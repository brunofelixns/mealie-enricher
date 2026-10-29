import math
import uuid

from ..compat import js_round
from ..config import HistorySettings
from ..models import (
    ExecutionEstimate,
    ExecutionRecord,
    ExecutionStatus,
    ExecutionTrigger,
    NutrientSet,
)
from .history import ExecutionHistory

RECIPES = [
    ("creamy-tomato-soup", "Creamy Tomato Soup"),
    ("spaghetti-bolognese", "Spaghetti Bolognese"),
    ("haehnchen-curry", "Hähnchen-Curry mit Reis"),
    ("grandmas-potato-salad", "Grandma's Potato Salad"),
    ("chocolate-chip-cookies", "Chocolate Chip Cookies"),
    ("lentil-stew", "Lentil Stew"),
    ("greek-salad", "Greek Salad"),
    ("beef-stir-fry", "Beef Stir Fry"),
    ("blueberry-pancakes", "Blueberry Pancakes"),
    ("pesto-pasta", "Pesto Pasta"),
    ("vegetarian-chili", "Vegetarian Chili"),
    ("caesar-salad", "Caesar Salad"),
    ("banana-bread", "Banana Bread"),
    ("mushroom-risotto", "Mushroom Risotto"),
    ("fish-tacos", "Fish Tacos"),
    ("apple-crumble", "Apple Crumble"),
    ("shakshuka", "Shakshuka"),
    ("ramen-broth", "Homemade Ramen Broth"),
    ("couscous-salad", "Couscous Salad"),
    ("chicken-noodle-soup", "Chicken Noodle Soup"),
    ("pad-thai", "Pad Thai"),
    ("schnitzel", "Wiener Schnitzel"),
    ("quinoa-bowl", "Quinoa Power Bowl"),
    ("tiramisu", "Tiramisu"),
    ("roasted-vegetables", "Roasted Vegetables"),
]
CALORIE_TAGS = ["calories-light", "calories-moderate", "calories-hearty", "calories-heavy"]
DIGEST_TAGS = ["digest-easy", "digest-moderate", "digest-slow"]


class _Random:
    """The original mulberry32 sequence, with JavaScript's unsigned 32-bit operations."""

    def __init__(self) -> None:
        self.a = 42

    def random(self) -> float:
        self.a += 0x6D2B79F5
        a = self.a & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    def integer(self, minimum: int, maximum: int) -> int:
        return math.floor(self.random() * (maximum - minimum + 1)) + minimum

    def pick(self, values: list[str]) -> str:
        return values[math.floor(self.random() * len(values))]

    def nutrients(self, kcal: int) -> NutrientSet:
        fat = self.integer(3, 45)
        return NutrientSet(
            kcal_per100g=kcal,
            protein_per100g=self.integer(5, 45),
            carbs_per100g=self.integer(10, 90),
            fat_per100g=fat,
            saturated_fat_per100g=js_round(fat * 0.4 * 10) / 10,
            trans_fat_per100g=0,
            unsaturated_fat_per100g=js_round(fat * 0.6 * 10) / 10,
            fiber_per100g=self.integer(1, 8),
            sugar_per100g=self.integer(2, 25),
            sodium_per100g=self.integer(100, 900),
            cholesterol_per100g=self.integer(0, 80),
        )


def seed_dev_history(settings: HistorySettings, history: ExecutionHistory) -> None:
    if not settings.seed_dev_data or history.get_history():
        return
    rand = _Random()
    now = int(history.clock_ms())
    statuses: list[ExecutionStatus] = ["processed"] * 18
    statuses.extend(["tags-added"] * 3)
    statuses.extend(["skipped"] * 2)
    statuses.extend(["manual", "filtered", "error", "running", "running"])
    triggers: list[ExecutionTrigger] = ["webhook"] * 15
    triggers.extend(["estimate"] * 5)
    triggers.extend(["backfill"] * 6)
    for index, status in enumerate(statuses):
        slug, name = RECIPES[index % len(RECIPES)]
        started = (
            now - rand.integer(1000, 8000)
            if index == len(statuses) - 1
            else now - 7200000 + math.floor(7200000 * index / len(statuses))
        )
        kcal = rand.integer(180, 940)
        calorie_tag, digest_tag = rand.pick(CALORIE_TAGS), rand.pick(DIGEST_TAGS)
        record = ExecutionRecord(
            id=str(uuid.uuid4()),
            started_at=started,
            updated_at=started,
            trigger=triggers[index % len(triggers)],
            slug=slug,
            recipe_name=name,
            status=status,
        )
        match status:
            case "processed":
                record.finished_at = started + rand.integer(900, 12000)
                record.changes = [
                    f"Set calories: {kcal} kcal/serving",
                    f"Auto-tags: {calorie_tag}, {digest_tag}",
                ]
                record.estimate = ExecutionEstimate(
                    nutrients=rand.nutrients(kcal),
                    matched_count=rand.integer(4, 16),
                    unmatched_count=rand.integer(0, 3),
                )
            case "tags-added":
                record.finished_at = started + rand.integer(200, 900)
                record.changes = [f"Added auto-tags: {calorie_tag}, {digest_tag}"]
            case "skipped":
                record.finished_at = started + rand.integer(40, 300)
                record.changes = ["Ingredients unchanged, tags already applied"]
            case "manual":
                record.finished_at = started + rand.integer(300, 1200)
                record.changes = [f"Preserved manual calories: {kcal} kcal"]
            case "filtered":
                record.finished_at = started + rand.integer(40, 300)
                record.changes = ["Recipe not tagged for estimation"]
            case "error":
                record.finished_at = started + rand.integer(1000, 30000)
                record.error = "Mealie API request timed out: PATCH http://mealie:9000/api/recipes"
        if record.finished_at is not None:
            record.duration_ms = record.finished_at - started
            record.updated_at = record.finished_at
        history.seed_record(record)
