import { createRequire } from "node:module"
import { readFile, writeFile, mkdir, copyFile, rm } from "node:fs/promises"
import { createServer } from "node:http"
import { pathToFileURL, fileURLToPath } from "node:url"
import { resolve, dirname } from "node:path"
import { mock } from "node:test"
import { runInNewContext } from "node:vm"
import { execFileSync } from "node:child_process"
import assert from "node:assert/strict"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..")
const reference = resolve(root, ".reference/mealie-calorie-estimator")
const output = resolve(root, "tests/fixtures/parity")
const work = resolve(root, ".reference/capture-work")
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: reference, encoding: "utf8" }).trim()
if (commit !== "c2dc71a1d8effe29375391f2fe50da94d27cfd7d") throw new Error("Wrong reference commit")
await mkdir(output, { recursive: true })
await mkdir(work, { recursive: true })
await rm(resolve(work, "cache.db"), { force: true })
for (const key of Object.keys(process.env)) {
  if (/^(MEALIE_|OFF_|LLM_|ESTIMATE_|EVENT_|CACHE_|HISTORY_|DEV_SEED_|LOG_LEVEL$|PORT$)/.test(key)) delete process.env[key]
}
Object.assign(process.env, { MEALIE_API_TOKEN: "test-token", MEALIE_URL: "http://127.0.0.1:18743", CACHE_DB_PATH: resolve(work, "cache.db"), LOG_LEVEL: "silent" })
const req = createRequire(resolve(reference, "package.json"))
const Fastify = req("fastify")
const cors = req("@fastify/cors")
const source = (name: string) => pathToFileURL(resolve(reference, "src", name)).href
const { config, getMealieToken } = await import(source("config.ts"))
const originalConfig = structuredClone(config)
mock.timers.enable({ apis: ["Date", "setTimeout"], now: 1700000000000 })
Object.defineProperty(performance, "now", { configurable: true, value: () => Date.now() - 1700000000000 })
config.openFoodFacts.searchRateLimit = 10000
config.openFoodFacts.productRateLimit = 10000
config.llm.rateLimit = 10000
config.events.debounceMs = 0

let requests: any[] = []
let responses: any[] = []
let offProducts: any[] = []
let offStatuses: number[] = []
let llmContent: any = "80"
let llmStatus = 200
let llmRaw: any = undefined
let backendStatus = 200
let currentRecipe: any
const clone = (value: any) => JSON.parse(JSON.stringify(value) ?? "null")
const normalize = (value: any) => {
  const ids = new Map()
  const text = JSON.stringify(value ?? null, (_key, val) => {
    if (typeof val === "string" && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(val)) {
      if (!ids.has(val)) ids.set(val, "00000000-0000-4000-8000-" + String(ids.size + 1).padStart(12, "0"))
      return ids.get(val)
    }
    return val
  })
  return JSON.parse(text)
}
globalThis.fetch = async (url: any, options: any = {}) => {
  const address = String(url)
  const record: any = { method: options.method ?? "GET", url: address }
  if (options.body) record.json = JSON.parse(options.body)
  requests.push(record)
  let status = 200
  let body: any
  if (address.includes("search.openfoodfacts.org/search?")) {
    status = offStatuses.shift() ?? 200
    body = { hits: offProducts }
  } else if (address.includes("/api/app/about/theme")) {
    body = { lightPrimary: "#123456", darkPrimary: "#abcdef", lightAccent: "invalid" }
  } else if (address.startsWith(config.llm.baseUrl)) {
    status = llmStatus
    body = llmRaw === undefined ? { choices: [{ message: { content: llmContent } }] } : llmRaw
  } else throw new Error("Unexpected external request: " + address)
  responses.push({ status, json: clone(body) })
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })
}
const backend = createServer(async (request, response) => {
  let raw = ""
  for await (const chunk of request) raw += chunk
  const record: any = { method: request.method, url: "http://127.0.0.1:18743" + request.url }
  if (raw) record.json = JSON.parse(raw)
  record.authorization = request.headers.authorization
  requests.push(record)
  let body: any = currentRecipe
  if (request.url?.startsWith("/api/recipes?")) body = { items: [{ slug: currentRecipe.slug }], total: 1, page: 1, total_pages: 1 }
  else if (request.url?.startsWith("/api/organizers/tags")) {
    if (request.method === "POST") {
      const name = JSON.parse(raw).name
      body = { id: name, name, slug: name.toLowerCase().replace(":", "-"), groupId: null }
    } else body = { items: [] }
  } else if (request.method === "PATCH") {
    currentRecipe = { ...currentRecipe, ...JSON.parse(raw) }
    body = currentRecipe
  }
  responses.push({ status: backendStatus, json: clone(body) })
  response.writeHead(backendStatus, { "content-type": "application/json" })
  response.end(JSON.stringify(body))
})
await new Promise<void>((done, reject) => { backend.once("error", reject); backend.listen(18743, "127.0.0.1", done) })

const cache = await import(source("utils/cache.ts"))
await cache.initCache()
const estimator = await import(source("services/estimator.ts"))
const units = await import(source("services/unit-converter.ts"))
const tagging = await import(source("services/tagging.ts"))
const llm = await import(source("services/llm-estimator.ts"))
const off = await import(source("services/off-client.ts"))
const history = await import(source("utils/execution-history.ts"))
const { SlugQueue } = await import(source("utils/slug-queue.ts"))
const theme = await import(source("services/mealie-theme.ts"))
const app = Fastify({ logger: false })
await app.register(cors)
for (const [file, fn] of [["webhook", "webhookRoutes"], ["estimate", "estimateRoutes"], ["backfill", "backfillRoutes"], ["history", "historyRoutes"]]) {
  const mod = await import(source("routes/" + file + ".ts"))
  app.register(mod[fn])
}
const index = await readFile(resolve(reference, "src/index.ts"), "utf8")
const healthRegistration = index.match(/app\.get\("\/health", \(\) => \{[\s\S]*?\n  \}\)/)?.[0]
if (!healthRegistration) throw new Error("Health source changed")
runInNewContext(healthRegistration, { app, Date })
await app.ready()

const nutrientKeys = ["kcal", "protein", "carbs", "fat", "saturatedFat", "transFat", "unsaturatedFat", "fiber", "sugar", "sodium", "cholesterol"]
const nutrients = (kcal = 100, fat: number | null = 5) => Object.fromEntries(nutrientKeys.map(k => [k + "Per100g", k === "kcal" ? kcal : k === "fat" ? fat : null]))
const unit = (name = "g", extras = {}) => ({ id: name, name, pluralName: null, abbreviation: name, standardQuantity: null, standardUnit: null, ...extras })
const ingredient = (name = "rice", quantity: any = 100, u: any = unit()) => ({ quantity, unit: u, food: { id: name, name, pluralName: null, aliases: [] }, note: null, display: name, title: null, originalText: null })
const recipe = (overrides = {}) => ({ slug: "synthetic-recipe", name: "Synthetic recipe", recipeYield: "2 servings", recipeYieldQuantity: null, recipeServings: 2, recipeIngredient: [ingredient()], nutrition: null, tags: [], extras: { foreign: "preserve" }, householdId: null, ...overrides })
const mealieNutrition = (calories = "500", fat: string | null = null) => ({ calories, carbohydrateContent: null, cholesterolContent: null, fatContent: fat, fiberContent: null, proteinContent: null, saturatedFatContent: null, sodiumContent: null, sugarContent: null, transFatContent: null, unsaturatedFatContent: null })
const product = (kcal = 100) => ({ product_name: "Synthetic product", nutriments: { "energy-kcal_100g": kcal, proteins_100g: 2, fat_100g: 0, carbohydrates_100g: 20 } })
const cases: any[] = []
const environment = () => ({
  ...Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("MEALIE_API_TOKEN_"))),
  MEALIE_API_TOKEN: "test-token", MEALIE_URL: "http://127.0.0.1:18743", OFF_LANGUAGE: config.openFoodFacts.language,
  OFF_SEARCH_RATE_LIMIT: String(config.openFoodFacts.searchRateLimit), OFF_PRODUCT_RATE_LIMIT: String(config.openFoodFacts.productRateLimit),
  LLM_ENABLED: String(config.llm.enabled), LLM_API_KEY: config.llm.apiKey, LLM_BASE_URL: config.llm.baseUrl,
  LLM_ENDPOINT_URL: config.llm.endpointUrl, LLM_MODEL: config.llm.model, LLM_RATE_LIMIT: String(config.llm.rateLimit), EVENT_DEBOUNCE_MS: "0",
  ESTIMATE_STRATEGY: config.estimate.strategy,
})
async function capture(id: string, area: string, contracts: string[], input: any, action: () => any) {
  requests = []; responses = []
  let result
  try { result = await action() } catch (error: any) { result = { error: error.message } }
  const item = { id, area, contracts, input, environment: environment(), external_responses: clone(responses), expected_requests: clone(requests), expected_result: normalize(result) }
  cases.push(item)
}
const flush = async () => { for (let i = 0; i < 50; i++) await new Promise(setImmediate) }
const tick = async (ms: number) => { mock.timers.tick(ms); await flush() }

await capture("config-defaults", "config", ["C39"], {}, () => {
  const childEnv = { ...process.env }
  for (const key of Object.keys(childEnv)) {
    if (/^(MEALIE_|OFF_|LLM_|ESTIMATE_|EVENT_|CACHE_|HISTORY_|DEV_SEED_|LOG_LEVEL$|PORT$)/.test(key)) delete childEnv[key]
  }
  childEnv.MEALIE_API_TOKEN = "test-token"
  const script = "import(" + JSON.stringify(source("config.ts")) + ").then(m=>console.log(JSON.stringify(m.config)))"
  return JSON.parse(execFileSync(process.execPath, [resolve(reference, "node_modules/tsx/dist/cli.mjs"), "--eval", script], { env: childEnv, encoding: "utf8" }))
})
cases.at(-1).environment = { MEALIE_API_TOKEN: "test-token" }
await capture("token-overrides", "config", ["C39"], { household_ids: [null, "abc-def", "ABC!upper", "unknown"] }, () => {
  process.env.MEALIE_API_TOKEN_abc_def = "synthetic-lower"
  process.env.MEALIE_API_TOKEN_ABC_upper = "synthetic-upper"
  return [null, "abc-def", "ABC!upper", "unknown"].map(id => getMealieToken(id))
})
for (const [id, changes] of [
  ["basic", {}], ["servings-zero", { recipeServings: 0 }], ["yield", { recipeServings: null, recipeYieldQuantity: 3 }],
  ["empty", { recipeIngredient: [] }], ["null-quantity", { recipeIngredient: [ingredient("rice", null)] }],
  ["unicode", { recipeIngredient: [ingredient("🥚", 0.1), ingredient("\ue000", 1e-7), ingredient("sal", -0)] }],
]) await capture("hash-" + id, "hash", ["C14", "C15", "C19"], recipe(changes), () => estimator.computeIngredientHash(recipe(changes)))
for (const name of ["g", "kg", "ml", "l", "cup", "tbsp", "tsp", "oz", "lb", "pinch", "dash", "clove", "piece", "slice", "unknown"]) {
  await capture("unit-" + name, "conversion", ["C20"], { quantity: 2, unit: unit(name) }, () => units.convertToGrams(2, unit(name)))
}
await capture("unit-standard", "conversion", ["C20"], { quantity: 2, unit: unit("custom", { standardQuantity: 240, standardUnit: "ml" }) }, () => units.convertToGrams(2, unit("custom", { standardQuantity: 240, standardUnit: "ml" })))
for (const kcal of [0, 349, 350, 600, 601, 850, 851]) for (const fat of [null, 0, 30]) {
  const input = nutrients(kcal, fat)
  await capture("tags-" + kcal + "-" + fat, "tags", ["C26", "C15"], input, () => tagging.computeTags(input))
}
for (const manual of [null, "", "  ", "0", "500"]) {
  const input = recipe({ nutrition: manual === null ? null : { calories: manual } })
  await capture("manual-" + String(manual).replaceAll(" ", "_"), "estimator", ["C16", "C17"], input, () => ({ manual: estimator.hasManualCalories(input), patch: estimator.buildManualAckPatch(input, estimator.computeIngredientHash(input)) }))
}
config.estimate.strategy = "tagged"
for (const tags of [[], [{ name: "EsTiMaTe", slug: "other" }], [{ name: "other", slug: "estimate" }]]) {
  await capture("strategy-" + cases.length, "estimator", ["C13"], recipe({ tags }), () => estimator.shouldEstimate(recipe({ tags })))
}
config.estimate.strategy = "all"
await capture("cache-normalization", "cache", ["C34"], { name: " RICE ", nutrients: nutrients() }, () => {
  cache.setCachedNutrients(" RICE ", nutrients())
  cache.setCachedLlmEstimate(" Cup ", " RICE ", 240)
  return { nutrients: cache.getCachedNutrients("rice"), grams: cache.getCachedLlmEstimate("cup", "rice"), miss: cache.getCachedNutrients("missing") ?? null }
})
for (const [id, override] of [
  ["normal", {}], ["zero-servings", { recipeServings: 0 }], ["fallback-yield", { recipeServings: null, recipeYieldQuantity: 4 }],
  ["ignored", { recipeIngredient: [ingredient("ignored", 0), ingredient("ignored", -2), ingredient("ignored", null), { ...ingredient(), food: null }] }],
  ["unmatched", { recipeIngredient: [ingredient("unknown", 1, unit("piece"))] }],
]) {
  offProducts = [product(101)]
  const input = recipe({ ...override, recipeIngredient: (override as any).recipeIngredient ?? [ingredient("food-" + id, 100)] })
  await capture("estimate-" + id, "estimator", ["C19", "C21", "C22", "C25"], input, async () => {
    const result = await estimator.estimateRecipe(input)
    return { result, patch: estimator.buildNutritionPatch(result, estimator.computeIngredientHash(input)) }
  })
}
config.llm.enabled = true
config.llm.apiKey = "synthetic-key"
config.llm.baseUrl = "https://llm.test/v1"
config.llm.endpointUrl = "/custom-completions"
for (const content of ["80", "80.9", "80 grams", "0", "-5", "abc", null]) {
  cache.clearLlmCache(); llmContent = content; llmRaw = undefined; llmStatus = 200
  const input = { quantity: 2, unit_name: "bunch", food_name: "synthetic greens" }
  await capture("llm-grams-" + String(content).replaceAll(" ", "_"), "llm", ["C24", "C33", "C40"], input, () => llm.estimateGrams(2, "bunch", "synthetic greens"))
}
for (const status of [429, 500]) {
  cache.clearLlmCache(); llmStatus = status
  await capture("llm-http-" + status, "llm", ["C33", "C40"], { quantity: 1, unit_name: "bunch", food_name: "greens", status }, () => llm.estimateGrams(1, "bunch", "greens"))
}
llmStatus = 200
for (const [id, content] of [["zeros", '{"kcal":100,"protein":0,"fat":0,"fiber":0}'], ["fenced", '\x60\x60\x60json\n{"kcal":250,"protein":4,"fat":8,"saturatedFat":10}\n\x60\x60\x60'], ["invalid", "bad"], ["zero-kcal", '{"kcal":0}']]) {
  cache.clearLlmCache(); llmContent = content
  await capture("llm-nutrients-" + id, "llm", ["C24", "C40"], { food_name: "synthetic food", content }, () => llm.estimateNutrients("synthetic food"))
}
config.llm.enabled = false
offProducts = []
await capture("off-no-match", "off", ["C23"], { food_name: "off-none" }, () => off.lookupNutrients("off-none"))
offProducts = [product(0), product(999)]
await capture("off-zero-first", "off", ["C23"], { food_name: "cup off-zero", unit_name: "cup" }, () => off.lookupNutrients("cup off-zero", "cup"))
offProducts = [{ product_name: "Incomplete", nutriments: { fat_100g: 5 } }]
await capture("off-no-kcal", "off", ["C23"], { food_name: "off-no-kcal" }, () => off.lookupNutrients("off-no-kcal"))
offStatuses = [503, 503, 503, 503]; offProducts = []
await capture("off-retries", "off", ["C31", "C32"], { food_name: "off-retry" }, async () => {
  const pending = off.lookupNutrients("off-retry")
  await flush(); for (const delay of [500, 1000, 2000]) await tick(delay)
  return await pending
})

for (const request of [
  { method: "GET", url: "/health" }, { method: "POST", url: "/webhook", payload: {} },
  { method: "POST", url: "/webhook", payload: { document_data: "%" } },
  { method: "POST", url: "/webhook", payload: { document_data: {} } },
  { method: "POST", url: "/webhook", payload: { document_data: { document_type: "other", recipe_slug: "x" } } },
  { method: "POST", url: "/estimate", payload: {} }, { method: "POST", url: "/estimate", payload: { content: null } },
  { method: "GET", url: "/estimator/history.json?since=abc" }, { method: "GET", url: "/estimator/history.json?since=" },
  { method: "OPTIONS", url: "/webhook", headers: { origin: "https://example.test", "access-control-request-method": "POST" } },
]) {
  history.clearHistory()
  await capture("http-" + cases.length, "http", ["C01", "C02", "C03", "C04", "C06", "C09", "C10", "C11", "C12"], request, async () => {
    const response = await app.inject(request)
    let body: any = response.body
    try { body = JSON.parse(body) } catch {}
    return { status: response.statusCode, body, content_type: response.headers["content-type"] ?? null, allow_origin: response.headers["access-control-allow-origin"] ?? null }
  })
}
for (const trigger of ["webhook", "estimate", "backfill"]) for (const state of ["normal", "manual", "unchanged", "tags-missing", "filtered", "error"]) {
  history.clearHistory(); backendStatus = state === "error" ? 503 : 200
  currentRecipe = recipe({ recipeIngredient: [ingredient("route-" + trigger + "-" + state)] })
  if (state === "manual") currentRecipe.nutrition = mealieNutrition()
  if (state === "unchanged" || state === "tags-missing") {
    currentRecipe.nutrition = mealieNutrition("500", "5")
    currentRecipe.extras.calorie_estimator_hash = estimator.computeIngredientHash(currentRecipe)
    if (state === "unchanged") {
      currentRecipe.tags = [{ name: "Calories:Moderate", id: "tag", slug: "calories-moderate", groupId: null }]
      currentRecipe.extras.calorie_estimator_tags = '["calories-moderate"]'
    }
  }
  config.estimate.strategy = state === "filtered" ? "tagged" : "all"
  offProducts = [product(101)]; offStatuses = []
  const input = { trigger, recipe: clone(currentRecipe), strategy: config.estimate.strategy, backend_status: backendStatus }
  await capture("route-" + trigger + "-" + state, "processing", ["C05", "C07", "C13", "C16", "C17", "C18", "C25", "C26", "C29", "C33", "C36", "C37"], input, async () => {
    const payload = trigger === "webhook" ? { document_data: encodeURIComponent(JSON.stringify({ documentType: "recipe", recipeSlug: currentRecipe.slug })) } : { content: { slug: currentRecipe.slug } }
    const response = await app.inject({ method: "POST", url: "/" + trigger.replace("webhook", "webhook").replace("backfill", "backfill"), payload })
    await flush()
    for (let i = 0; i < 20 && history.getHistory().some(r => r.status === "running"); i++) await flush()
    const records = history.getHistory()
    const expectedStatus = state === "filtered" ? "filtered" : state === "error" ? "error" : trigger === "estimate" ? "processed" : state === "manual" ? "manual" : state === "unchanged" ? "skipped" : state === "tags-missing" ? "tags-added" : "processed"
    if (!(state === "error" && trigger === "backfill")) {
      assert.equal(records.length, 1, "Missing execution for " + trigger + "/" + state)
      assert.equal(records[0].status, expectedStatus, "Unexpected execution for " + trigger + "/" + state)
    }
    return { status: response.statusCode, body: JSON.parse(response.body), history: records, patches: requests.filter(r => r.method === "PATCH").map(r => r.json) }
  })
  if (cases.at(-1).expected_result?.error) throw new Error("Route capture failed: " + cases.at(-1).expected_result.error)
}
backendStatus = 200; config.estimate.strategy = "all"; history.clearHistory()
await capture("history-states", "history", ["C09", "C10", "C35", "C36", "C37"], {}, () => {
  for (const status of ["processed", "tags-added", "manual", "skipped", "filtered", "running", "error"]) {
    const handle = history.recordStart({ trigger: "estimate", slug: status })
    handle.setRecipe("Synthetic " + status, null)
    if (status === "error") handle.fail(new Error("x".repeat(350)))
    else if (status !== "running") handle.complete(status, [status])
  }
  return { all: history.getHistory(), since: history.getHistory(Date.now()) }
})
await capture("history-max", "history", ["C35"], {}, () => {
  history.clearHistory()
  for (let i = 0; i < 201; i++) history.recordStart({ trigger: "estimate", slug: "recipe-" + i })
  return { count: history.getHistory().length, slugs: history.getHistory().map(r => r.slug) }
})
await capture("history-html", "http", ["C08", "C38"], { method: "GET", url: "/estimator/history" }, async () => {
  const response = await app.inject({ method: "GET", url: "/estimator/history" })
  return { status: response.statusCode, content_type: response.headers["content-type"], cache_control: response.headers["cache-control"], html: response.body }
})
await capture("queue-burst", "queue", ["C27", "C28"], { debounce_ms: 100 }, async () => {
  const queue = new SlugQueue(100); const order: any[] = []
  const pending = [queue.run("same", "webhook", async () => { order.push("webhook") }), queue.run("same", "estimate", async () => { order.push("estimate") }), queue.run("same", "webhook", async () => { order.push("duplicate") })]
  await tick(60); const before = clone(order)
  pending.push(queue.run("same", "webhook", async () => { order.push("late") }))
  await tick(60); const middle = clone(order)
  await tick(40); await Promise.all(pending)
  return { before, middle, order }
})
await capture("queue-failure", "queue", ["C27", "C28"], {}, async () => {
  const queue = new SlugQueue(100); const order: any[] = []
  const failure = queue.runNow("same", async () => { throw new Error("boom") }).catch(e => e.message)
  const success = queue.runNow("same", async () => { order.push("recovered") })
  return { error: await failure, order: (await success, order) }
})
config.openFoodFacts.searchRateLimit = 2
const freshLimiter = await import(source("utils/rate-limiter.ts") + "?capture")
await capture("limiter-window", "limiter", ["C30"], { capacity: 2, duration_ms: 60000 }, async () => {
  await freshLimiter.waitForRateLimit(freshLimiter.RateLimitType.Search)
  await freshLimiter.waitForRateLimit(freshLimiter.RateLimitType.Search)
  let done = false
  const pending = freshLimiter.waitForRateLimit(freshLimiter.RateLimitType.Search).then(() => { done = true })
  await flush(); await tick(1000); const afterOneSecond = done
  for (let i = 1; i < 60; i++) await tick(1000)
  await pending
  return { afterOneSecond, afterMinute: done }
})
await capture("dev-seed", "history", ["C35", "C36", "C38"], { now_ms: Date.now() }, async () => {
  history.clearHistory()
  config.history.seedDevData = true
  const { seedDevHistory } = await import(source("utils/dev-seed.ts"))
  seedDevHistory()
  config.history.seedDevData = false
  return history.getHistory()
})
for (const [name, request] of [
  ["malformed-json", { method: "POST", url: "/webhook", headers: { "content-type": "application/json" }, payload: "{" }],
  ["empty-json", { method: "POST", url: "/estimate", headers: { "content-type": "application/json" }, payload: "" }],
  ["unsupported-media", { method: "POST", url: "/estimate", headers: { "content-type": "application/octet-stream" }, payload: "{}" }],
  ["plain-text", { method: "POST", url: "/webhook", headers: { "content-type": "text/plain" }, payload: '{"document_data":{"documentType":"other","recipeSlug":"x"}}' }],
  ["null-webhook", { method: "POST", url: "/webhook", headers: { "content-type": "application/json" }, payload: "null" }],
  ["null-estimate", { method: "POST", url: "/estimate", headers: { "content-type": "application/json" }, payload: "null" }],
  ["absent-webhook", { method: "POST", url: "/webhook" }],
  ["absent-estimate", { method: "POST", url: "/estimate" }],
  ["invalid-preflight", { method: "OPTIONS", url: "/webhook" }],
  ["not-found", { method: "GET", url: "/missing" }],
  ["head-health", { method: "HEAD", url: "/health" }],
] as const) {
  await capture("http-edge-" + name, "http", ["C12"], { ...request, raw: true }, async () => {
    const response = await app.inject(request)
    let body: any = response.body
    try { body = JSON.parse(body) } catch {}
    return { status: response.statusCode, body, content_type: response.headers["content-type"] ?? null, allow_origin: response.headers["access-control-allow-origin"] ?? null }
  })
}
for (const [name, value] of [
  ["numeric-string-quantity", recipe({ recipeIngredient: [ingredient("numeric", "02.0", unit("g"))] })],
  ["numeric-string-servings", recipe({ recipeServings: "02" as any, recipeYieldQuantity: "04.0" as any })],
] as const) {
  await capture("hash-" + name, "hash", ["C14", "C15"], value, () => estimator.computeIngredientHash(value))
}
const stringRecipe = recipe({ recipeServings: "02" as any, recipeIngredient: [ingredient("numeric-string-food", "100.0", unit("g"))] })
offProducts = [product(101)]
await capture("estimate-numeric-string", "estimator", ["C15", "C19", "C22", "C25"], stringRecipe, async () => {
  const result = await estimator.estimateRecipe(stringRecipe)
  return { result, patch: estimator.buildNutritionPatch(result, estimator.computeIngredientHash(stringRecipe)) }
})
await tick(5000)
await copyFile(resolve(work, "cache.db"), resolve(output, "legacy-cache.db"))
const manifest: any = { upstream_commit: commit, upstream_version: "1.12.3", normalization: ["execution UUIDs", "clock timestamps and durations"], clock_epoch_ms: 1700000000000, cases: [] }
for (const item of cases) {
  const filename = item.id + ".json"
  await writeFile(resolve(output, filename), JSON.stringify(item, null, 2) + "\n", "utf8")
  manifest.cases.push({ id: item.id, area: item.area, contracts: item.contracts, file: filename })
}
manifest.covered_contracts = [...new Set(cases.flatMap(c => c.contracts))].sort()
const missing = Array.from({ length: 40 }, (_, i) => "C" + String(i + 1).padStart(2, "0")).filter(c => !manifest.covered_contracts.includes(c))
if (missing.length) throw new Error("Uncovered contracts: " + missing.join(", "))
await writeFile(resolve(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8")
await app.close()
backend.close()
mock.timers.reset()
console.log(JSON.stringify({ cases: cases.length, contracts: manifest.covered_contracts.length, commit }))
process.exit(0)
