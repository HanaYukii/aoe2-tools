"""Ladder ratings from the game's public API, the one its leaderboards use."""
import json
import urllib.parse
import urllib.request

API = 'https://aoe-api.worldsedgelink.com/community/leaderboard/GetPersonalStat'
RM_1V1 = 3
RM_TEAM = 4
TIMEOUT_SECONDS = 3


def fetch_ratings(profile_ids, timeout=TIMEOUT_SECONDS):
    """{profile_id: {leaderboard_id: rating}}; raises OSError or ValueError."""
    ids = json.dumps(sorted(profile_ids), separators=(',', ':'))
    query = urllib.parse.urlencode({'title': 'age2', 'profile_ids': ids})
    with urllib.request.urlopen(f'{API}?{query}', timeout=timeout) as response:
        data = json.load(response)
    if data.get('result', {}).get('code') != 0:
        raise ValueError(f'API result {data.get("result")}')
    profile_of_group = {g['id']: g['members'][0]['profile_id']
                        for g in data.get('statGroups', []) if len(g['members']) == 1}
    ratings = {}
    for stat in data.get('leaderboardStats', []):
        profile_id = profile_of_group.get(stat['statgroup_id'])
        if profile_id is not None:
            ratings.setdefault(profile_id, {})[stat['leaderboard_id']] = stat['rating']
    return ratings
