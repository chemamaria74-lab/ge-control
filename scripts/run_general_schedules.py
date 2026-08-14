"""Punto de entrada para ejecutar programaciones desde un cron independiente."""

from __future__ import annotations

import json
import sys

from services.general_schedule_worker import run_due_schedules


def main() -> int:
    results = run_due_schedules()
    print(json.dumps(results, ensure_ascii=False, default=str))
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
