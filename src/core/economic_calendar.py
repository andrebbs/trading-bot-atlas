"""
Economic calendar for forex trading alerts.
Uses locally cached data (no external API).
Calendar data can be updated manually or via cron job.
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional


CALENDAR_DATA_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'eco_events.json')

# Default events for demo (19/05/2026)
DEFAULT_EVENTS = [
    {
        'event': 'Employment Change',
        'country': 'US',
        'importance': 'high',
        'date': '2026-05-19',
        'time': '14:30',
        'forecast': '250K',
        'previous': '272K',
    },
    {
        'event': 'Core CPI MoM',
        'country': 'US',
        'importance': 'high',
        'date': '2026-05-20',
        'time': '12:30',
        'forecast': '0.3%',
        'previous': '0.4%',
    },
    {
        'event': 'Inflation Rate YoY',
        'country': 'EU',
        'importance': 'high',
        'date': '2026-05-21',
        'time': '09:00',
        'forecast': '2.1%',
        'previous': '2.4%',
    },
    {
        'event': 'Interest Rate Decision',
        'country': 'JP',
        'importance': 'high',
        'date': '2026-05-22',
        'time': '05:00',
        'forecast': '0.1%',
        'previous': '0.1%',
    },
    {
        'event': 'Retail Sales MoM',
        'country': 'GB',
        'importance': 'medium',
        'date': '2026-05-23',
        'time': '08:00',
        'forecast': '0.5%',
        'previous': '-1.0%',
    },
]


def _ensure_calendar_file():
    """Create default calendar file if it doesn't exist."""
    if not os.path.exists(CALENDAR_DATA_FILE):
        try:
            os.makedirs(os.path.dirname(CALENDAR_DATA_FILE), exist_ok=True)
            with open(CALENDAR_DATA_FILE, 'w') as f:
                json.dump({'events': DEFAULT_EVENTS, 'updated': datetime.utcnow().isoformat()}, f, indent=2)
        except Exception:
            pass


def _load_calendar() -> List[Dict]:
    """Load calendar events from local file."""
    _ensure_calendar_file()
    try:
        if os.path.exists(CALENDAR_DATA_FILE):
            with open(CALENDAR_DATA_FILE, 'r') as f:
                data = json.load(f)
                return data.get('events', DEFAULT_EVENTS)
    except Exception:
        pass
    return DEFAULT_EVENTS


def get_todays_events() -> List[Dict]:
    """Get calendar events for today only."""
    today = datetime.utcnow().strftime('%Y-%m-%d')
    events = _load_calendar()
    return [e for e in events if e.get('date', '').startswith(today)]


def get_upcoming_high_impact(minutes_ahead: int = 60) -> List[Dict]:
    """
    Get high-impact events happening in the next N minutes.
    Used for alerts before major releases.
    """
    events = _load_calendar()
    now = datetime.utcnow()
    upcoming_cutoff = now + timedelta(minutes=minutes_ahead)
    
    high_impact_events = [
        e for e in events 
        if e.get('importance', '').lower() == 'high' 
        and e.get('date') and e.get('time')
    ]
    
    result = []
    for evt in high_impact_events:
        try:
            evt_str = '%s %s' % (evt.get('date'), evt.get('time'))
            evt_dt = datetime.strptime(evt_str, '%Y-%m-%d %H:%M')
            if now < evt_dt <= upcoming_cutoff:
                result.append(evt)
        except Exception:
            pass
    
    return result


def format_event(evt: Dict) -> str:
    """Format event for telegram message."""
    title = evt.get('event', 'Unknown')
    country = evt.get('country', '')
    importance = evt.get('importance', 'low').upper()
    time_str = evt.get('time', '')
    forecast = evt.get('forecast', 'N/A')
    previous = evt.get('previous', 'N/A')
    
    icon = '🔴' if importance == 'HIGH' else '🟡' if importance == 'MEDIUM' else '⚪'
    
    return (
        f"{icon} *{title}*\n"
        f"  Country: {country}\n"
        f"  Time: {time_str}\n"
        f"  Forecast: {forecast} | Previous: {previous}"
    )


def get_calendar_summary() -> str:
    """Get summary of today's events for telegram."""
    events = get_todays_events()
    
    if not events:
        return "📅 Nenhum evento econômico importante para hoje."
    
    # Group by importance
    high = [e for e in events if e.get('importance', '').lower() == 'high']
    medium = [e for e in events if e.get('importance', '').lower() == 'medium']
    
    msg = "📅 *Calendario Economico - Hoje (%s)*\n\n" % datetime.now().strftime('%d/%m/%Y')
    
    if high:
        msg += "*🔴 ALTO IMPACTO:*\n"
        for e in high[:5]:
            msg += "  • %s (%s) às %s\n" % (e.get('event'), e.get('country'), e.get('time'))
    
    if medium:
        msg += "\n*🟡 MEDIO IMPACTO:*\n"
        for e in medium[:5]:
            msg += "  • %s (%s) às %s\n" % (e.get('event'), e.get('country'), e.get('time'))
    
    return msg
