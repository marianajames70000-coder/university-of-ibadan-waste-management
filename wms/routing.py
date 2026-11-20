"""Route planning: select bins and pickups to visit, order stops by nearest neighbour."""
from math import radians, sin, cos, asin, sqrt
DEPOT = (7.3775, 3.9470)   # municipal depot (University of Ibadan area)
def haversine(a, b):
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 2*6371.0*asin(sqrt(h))
def tour_length(points, depot=DEPOT):
    if not points: return 0.0
    t, cur = 0.0, depot
    for p in points: t += haversine(cur, p); cur = p
    return t + haversine(cur, depot)
def nearest_neighbour(points, depot=DEPOT):
    """points: list of (lat, lon, payload). Returns the list reordered."""
    left, order, cur = list(points), [], depot
    while left:
        nxt = min(left, key=lambda p: haversine(cur, (p[0], p[1])))
        left.remove(nxt); order.append(nxt); cur = (nxt[0], nxt[1])
    return order
def plan(points, depot=DEPOT):
    order = nearest_neighbour(points, depot)
    return order, tour_length([(p[0], p[1]) for p in order], depot), tour_length([(p[0], p[1]) for p in points], depot)
