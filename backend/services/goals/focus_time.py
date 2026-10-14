"""Day allocation from confirmed activity only, never from paused wall-clock gaps."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def daily_totals(segments, timezone_name):
    try:
        zone=ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError,ValueError,TypeError) as exc:
        raise ValueError('无效展示时区') from exc
    totals={}
    for segment in segments:
        cursor=float(segment['started_at'])
        remaining=int(segment['active_ms'])
        while remaining>0:
            local=datetime.fromtimestamp(cursor,zone)
            midnight=datetime.combine(local.date()+timedelta(days=1),time.min,zone).timestamp()
            count=min(remaining,max(1,round((midnight-cursor)*1000)))
            day=local.date().isoformat()
            totals[day]=totals.get(day,0)+count
            cursor+=count/1000
            remaining-=count
    return [{'date':day,'active_ms':value} for day,value in sorted(totals.items(),reverse=True)]
