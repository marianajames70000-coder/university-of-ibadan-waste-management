# Waste Management System for a Municipality
**Case study: University of Ibadan and its environs (Ibadan, Oyo State, Nigeria)** · CSC 476 semester project · Group 33

A web application that lets residents request waste pickups and report illegal dumping, lets municipal staff monitor bin fill levels, plan the shortest collection routes and track recycling, and lets collection crews record what they collected.

## Group 33 and roles
| Member | Matric no. | Role |
|---|---|---|
| Oni Moyinoluwa | E052022 | **Group leader**, project manager and integration lead |
| Onojah David | E051987 | Backend developer (routing and workflow logic) |
| Osagiede Israel | E052033 | Database designer and data analyst |
| Menye Daniel | E052039 | UI/UX and front-end developer |
| Adunmo Jesufemi | E052035 | Quality assurance and security tester |

(The group list gives five names; a sixth member and the supervisor can be added in the report front matter.)

## Run it
```
pip install -r requirements.txt
python wsgi.py            # http://127.0.0.1:5000  (creates and seeds the SQLite database)
python -m unittest discover -s tests -t .     # 35 tests
PYTHONPATH=. python docs/benchmark.py         # route-ordering benchmark
```
Demo logins: `admin@wms.test / Admin@12345`, `collector1@wms.test / Collect@123`, `resident1@wms.test / Resident@123`.

## Features
Resident: register, request pickups (general, recyclable, bulky, hazardous), cancel pending requests, report dumping with an optional photo. Admin: dashboard, bin monitoring, route planning (full bins plus pending pickups, nearest-neighbour ordering), dumping-report handling, recycling log, analytics, CSV export, user management, audit log. Collector: assigned routes, start route, record weight per stop.

## Security
Scrypt password hashing, lockout after 5 failures (15 min), 30-minute session timeout, CSRF tokens, CSP and other headers, role-based access, upload signature check, parameterised SQL, audit log.

## Known limitations
Bin sensors are simulated (fill levels are set by hand or by seed data); no SMS/e-mail provider; routing is a heuristic over straight-line distance, not road distance; SQLite is used for the prototype.
