CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 phone TEXT, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN('resident','collector','admin')),
 zone_id INTEGER REFERENCES zones(id), failed_logins INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS zones(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, collection_day TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bins(
 id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id INTEGER NOT NULL REFERENCES zones(id), label TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN('general','recyclable','organic')), capacity_l INTEGER NOT NULL,
 fill_pct INTEGER NOT NULL DEFAULT 0 CHECK(fill_pct BETWEEN 0 AND 100), lat REAL NOT NULL, lon REAL NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS pickup_requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, resident_id INTEGER NOT NULL REFERENCES users(id),
 zone_id INTEGER NOT NULL REFERENCES zones(id), address TEXT NOT NULL,
 waste_type TEXT NOT NULL CHECK(waste_type IN('general','recyclable','bulky','hazardous')),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','scheduled','collected','cancelled')),
 route_id INTEGER REFERENCES routes(id), preferred_date TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, version INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS dumping_reports(
 id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER NOT NULL REFERENCES users(id),
 zone_id INTEGER NOT NULL REFERENCES zones(id), location TEXT NOT NULL, description TEXT NOT NULL,
 photo TEXT, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','investigating','resolved')),
 resolution TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS routes(
 id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id INTEGER NOT NULL REFERENCES zones(id), route_date TEXT NOT NULL,
 vehicle TEXT NOT NULL, collector_id INTEGER NOT NULL REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN('planned','in_progress','completed')),
 distance_km REAL NOT NULL DEFAULT 0, naive_km REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS route_stops(
 id INTEGER PRIMARY KEY AUTOINCREMENT, route_id INTEGER NOT NULL REFERENCES routes(id), seq INTEGER NOT NULL,
 bin_id INTEGER REFERENCES bins(id), request_id INTEGER REFERENCES pickup_requests(id),
 done INTEGER NOT NULL DEFAULT 0, weight_kg REAL);
CREATE TABLE IF NOT EXISTS recycling_log(
 id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id INTEGER NOT NULL REFERENCES zones(id),
 material TEXT NOT NULL CHECK(material IN('plastic','paper','glass','metal','organic')),
 kg REAL NOT NULL CHECK(kg>0), logged_by INTEGER NOT NULL REFERENCES users(id), logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT NOT NULL, detail TEXT, at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
