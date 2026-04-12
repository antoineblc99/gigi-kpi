"""Rebuild all BASE sheets + dashboards. Run daily to keep everything fresh."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))

import rebuild_data_funnel_follow
import rebuild_data_funnel_vsl
import build_global
import build_funnel_follow
import build_funnel_vsl
import build_closer
import build_setter
import build_creatives
from auth import get_sheets_service  # noqa: E402


def main():
    print("=" * 60)
    print("REBUILD BASE DATA")
    print("=" * 60)
    rebuild_data_funnel_follow.main()
    rebuild_data_funnel_vsl.main()

    print("\n" + "=" * 60)
    print("REBUILD DASHBOARDS")
    print("=" * 60)
    s = get_sheets_service()
    build_global.build_benchmarks(s)
    build_global.build_dashboard_global(s)
    build_funnel_follow.build(s)
    build_funnel_vsl.build(s)
    build_closer.build(s)
    build_setter.build(s)
    build_creatives.build(s)

    print("\n✅ All done.")


if __name__ == "__main__":
    main()
