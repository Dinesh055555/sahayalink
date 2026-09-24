"""Build and seed the SahayaLink SQLite database from the real analysis output."""
import sqlite3, json, os, re, hashlib, random
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(HERE, 'sahayalink.db')
random.seed(42)

def norm(x):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9\s]', ' ', str(x).lower())).strip() if x else ''

# ---- load real data ----
cases = json.load(open(os.path.join(HERE, 'app_data.json')))
hotspots = json.load(open(os.path.join(HERE, 'village_hotspots.json')))
geo = {}
import csv
with open(os.path.join(ROOT, 'geography_reference.csv'), encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        geo[norm(r['village'])] = {'canonical': r['village'], 'district': r['district'],
                                   'block': r['block'], 'lat': r['latitude'], 'lng': r['longitude'],
                                   'conn': r['mobile_connectivity'], 'road': r['road_access']}

def canonical_village(v):
    n = norm(v)
    if n in geo:
        return geo[n]['canonical'], geo[n]['district'], geo[n]['block']
    # fuzzy: closest geo village by prefix
    for k in geo:
        if k.startswith(n[:5]) or n.startswith(k[:5]):
            return geo[k]['canonical'], geo[k]['district'], geo[k]['block']
    return str(v).title(), '', ''

def pin(s):
    return hashlib.sha256(s.encode()).hexdigest()

# ---- schema ----
con = sqlite3.connect(DB)
c = con.cursor()
c.executescript('''
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS worker_villages;
DROP TABLE IF EXISTS worklist;
DROP TABLE IF EXISTS action_log;
DROP TABLE IF EXISTS points_ledger;
DROP TABLE IF EXISTS point_rules;
DROP TABLE IF EXISTS villages;

CREATE TABLE users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE, name TEXT, role TEXT,
  pin_hash TEXT, district TEXT, block TEXT);

CREATE TABLE villages(
  village TEXT PRIMARY KEY, district TEXT, block TEXT, lat REAL, lng REAL,
  mobile_connectivity TEXT, road_access TEXT);

CREATE TABLE worker_villages(
  user_id INTEGER, village TEXT,
  PRIMARY KEY(user_id, village));

CREATE TABLE worklist(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_date TEXT, episode_id TEXT, patient_ref TEXT, village TEXT,
  district TEXT, priority TEXT, risk_pct REAL, dropout_stage TEXT,
  reason TEXT, recommended_action TEXT, assigned_cadre TEXT,
  assigned_user_id INTEGER, distance_km REAL, mobile_connectivity TEXT,
  diagnosis_group TEXT, preferred_language TEXT, age TEXT, gender TEXT,
  facility_name TEXT, attempt_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending',   -- pending | resolved | unreachable | escalated
  is_hard INTEGER DEFAULT 0);

CREATE TABLE action_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  worklist_id INTEGER, user_id INTEGER, outcome TEXT, note TEXT,
  points_awarded INTEGER DEFAULT 0, ts TEXT);

CREATE TABLE points_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER, points INTEGER, reason TEXT, ts TEXT);

CREATE TABLE point_rules(
  rule TEXT PRIMARY KEY, points INTEGER, note TEXT);
''')

# point rules (difficulty-weighted)
c.executemany('INSERT INTO point_rules VALUES(?,?,?)', [
    ('resolve_critical', 10, 'Resolved a Critical-priority follow-up'),
    ('resolve_high', 6, 'Resolved a High-priority follow-up'),
    ('resolve_other', 4, 'Resolved a follow-up'),
    ('hard_bonus', 3, 'Bonus: reached a patient in a far / weak-signal village'),
    ('attempt', 1, 'Logged a contact attempt (even if unreachable)'),
])

# ---- villages ----
seen = {}
for h in hotspots:
    v = h['village']; n = norm(v)
    g = geo.get(n)
    if g:
        seen[g['canonical']] = (g['district'], g['block'], g['lat'], g['lng'], g['conn'], g['road'])
for n, g in geo.items():
    seen.setdefault(g['canonical'], (g['district'], g['block'], g['lat'], g['lng'], g['conn'], g['road']))
for v, (d, b, lat, lng, conn, road) in seen.items():
    c.execute('INSERT OR IGNORE INTO villages VALUES(?,?,?,?,?,?,?)',
              (v, d, b, float(lat) if lat else None, float(lng) if lng else None, conn, road))

# ---- ASHA + CHO users, assigned by block ----
# group villages by (district, block)
blocks = {}
for v, (d, b, *_ ) in seen.items():
    blocks.setdefault((d, b), []).append(v)

ASHA_NAMES = ['Lakshmi','Padma','Anjali','Sunitha','Radha','Kavitha','Sarala','Manjula',
              'Bharathi','Vijaya','Latha','Sridevi','Nirmala','Saroja','Renuka','Shobha',
              'Geetha','Uma','Devi','Aruna','Jyothi','Sujatha','Madhavi','Rani']
CHO_NAMES = ['Dr. Ramesh','Dr. Sneha','Dr. Kiran','Dr. Anitha','Dr. Prasad','Dr. Meena']

uid = 1
asha_idx = 0; cho_idx = 0
block_workers = {}  # (d,b) -> list of asha user_ids
for (d, b), vills in sorted(blocks.items()):
    if not b: continue
    # 2 ASHAs per block so reassignment has somewhere to go
    ids = []
    for _ in range(2):
        name = ASHA_NAMES[asha_idx % len(ASHA_NAMES)]; asha_idx += 1
        uname = f'asha{uid}'
        c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
                  (uid, uname, name, 'ASHA', pin('1234'), d, b))
        # split villages between the two ASHAs
        ids.append(uid); uid += 1
    # Both ASHAs in a block co-cover every village, so an unreachable case can be
    # handed to the OTHER worker next day. Primary assignment still alternates by village.
    for v in vills:
        for a in ids:
            c.execute('INSERT INTO worker_villages VALUES(?,?)', (a, v))
    block_workers[(d, b)] = ids
    block_workers[(d, b, 'primary')] = {v: ids[i % 2] for i, v in enumerate(vills)}
    # 1 CHO per block
    name = CHO_NAMES[cho_idx % len(CHO_NAMES)]; cho_idx += 1
    c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
              (uid, f'cho{uid}', name, 'CHO', pin('4321'), d, b))
    for v in vills:
        c.execute('INSERT INTO worker_villages VALUES(?,?)', (uid, v))
    block_workers[(d, b, 'CHO')] = uid; uid += 1

# a district supervisor login
c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
          (uid, 'supervisor', 'District Supervisor', 'SUPERVISOR', pin('0000'), '', ''))
uid += 1

# ---- seed today's worklist from real cases ----
today = date.today().isoformat()
HARD_CONN = {'Weak','Very weak','Poor'}
placed = 0; unplaced = 0
for r in cases:
    cv, cd, cb = canonical_village(r['village'])
    key = (cd, cb)
    ashas = block_workers.get(key)
    if not ashas:
        # fallback: any block in same district
        cand = [k for k in block_workers if len(k)==2 and k[0]==cd]
        ashas = block_workers.get(cand[0]) if cand else None
    if not ashas:
        unplaced += 1; continue
    # primary ASHA for this village (both co-cover it for reassignment)
    primary = block_workers.get((cd, cb, 'primary'), {})
    assigned = primary.get(cv, ashas[0])
    dist = r.get('distance_km') or 0
    hard = 1 if (str(r.get('mobile_connectivity')) in HARD_CONN or (dist and float(dist) >= 15)) else 0
    # resupply/clinical goes to CHO
    cadre = 'CHO' if ('resupply' in str(r['recommended_action']) or 'review' in str(r['recommended_action']).lower()) else 'ASHA'
    if cadre == 'CHO':
        assigned = block_workers.get((cd, cb, 'CHO'), assigned)
    c.execute('''INSERT INTO worklist(work_date,episode_id,patient_ref,village,district,priority,risk_pct,
        dropout_stage,reason,recommended_action,assigned_cadre,assigned_user_id,distance_km,
        mobile_connectivity,diagnosis_group,preferred_language,age,gender,facility_name,is_hard)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (today, r['episode_id'], r['patient_ref'], cv, cd, r['priority'], r['risk_pct'],
         r.get('predicted_dropout_stage'), r['reason'], r['recommended_action'], cadre, assigned,
         dist, r.get('mobile_connectivity'), r.get('diagnosis_group'), r.get('preferred_language'),
         str(r.get('age')), r.get('gender'), r.get('facility_name'), hard))
    placed += 1

con.commit()
n_users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
n_asha = c.execute("SELECT COUNT(*) FROM users WHERE role='ASHA'").fetchone()[0]
n_cho = c.execute("SELECT COUNT(*) FROM users WHERE role='CHO'").fetchone()[0]
print(f'DB seeded: {n_users} users ({n_asha} ASHA, {n_cho} CHO), {placed} cases placed, {unplaced} unplaced, {len(seen)} villages')
# print a sample ASHA login with cases
row = c.execute('''SELECT u.username,u.name,u.district,u.block,COUNT(w.id)
    FROM users u JOIN worklist w ON w.assigned_user_id=u.id
    WHERE u.role='ASHA' GROUP BY u.id ORDER BY COUNT(w.id) DESC LIMIT 3''').fetchall()
print('Top ASHA logins (username / pin 1234):')
for un,nm,d,b,cnt in row: print(f'  {un}  {nm}  {b},{d}  {cnt} cases')
con.close()
