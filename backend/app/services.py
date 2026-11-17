import hashlib, math, time, requests
from urllib.parse import quote
from .config import OPENCHARGEMAP_API_KEY as OCM_KEY, BEE_API_BASE, PHOTON_API_BASE, OSRM_API_BASE

INDIA = {"min_lat": 6.0, "max_lat": 38.0, "min_lng": 67.0, "max_lng": 99.0}
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "EVChargeRoute-India/4.1 (educational EV route planner)"})

def _in_india(lat, lng):
    return lat is not None and lng is not None and INDIA["min_lat"] <= float(lat) <= INDIA["max_lat"] and INDIA["min_lng"] <= float(lng) <= INDIA["max_lng"]

def parse_duration_seconds(value):
    if isinstance(value,(int,float)): return float(value)
    if not value: return 0.0
    try: return float(str(value).rstrip("s"))
    except Exception: return 0.0

def geocode(address):
    # Photon bounding box confines search results to India. Coordinates are checked again.
    params={"q":address,"limit":6,"lang":"en","bbox":"67,6,99,38"}
    r=SESSION.get(f"{PHOTON_API_BASE}/api/",params=params,timeout=15); r.raise_for_status()
    features=r.json().get("features") or []
    for feature in features:
        coords=(feature.get("geometry") or {}).get("coordinates") or []
        if len(coords)<2: continue
        lng,lat=float(coords[0]),float(coords[1])
        if not _in_india(lat,lng): continue
        p=feature.get("properties") or {}
        parts=[p.get(k) for k in ("name","street","district","city","state","country") if p.get(k)]
        return {"lat":lat,"lng":lng,"formatted":", ".join(dict.fromkeys(parts)) or address}
    raise ValueError(f"Could not find '{address}' within India. Try a more specific Indian city or address.")

def compute_route(origin,destination,intermediates=None,traffic=False):
    points=[origin]+(intermediates or [])+[destination]
    if any(not _in_india(p.get("lat"),p.get("lng")) for p in points): raise ValueError("Only routes within India are supported.")
    coords=";".join(f'{float(p["lng"])},{float(p["lat"])}' for p in points)
    url=f"{OSRM_API_BASE}/route/v1/driving/{coords}"
    r=SESSION.get(url,params={"overview":"full","geometries":"polyline","steps":"false","alternatives":"false"},timeout=25); r.raise_for_status()
    data=r.json(); routes=data.get("routes") or []
    if not routes: raise ValueError("No drivable road route was found between these Indian locations.")
    route=routes[0]
    return {"distance_km":round(route.get("distance",0)/1000,2),"duration_min":round(route.get("duration",0)/60,1),"static_duration_min":round(route.get("duration",0)/60,1),"polyline":route.get("geometry","")}

def route_matrix_batch(origins,destinations):
    if not origins or not destinations: return []
    points=list(origins)+list(destinations)
    if any(not _in_india(p.get("lat"),p.get("lng")) for p in points): return []
    coords=";".join(f'{float(p["lng"])},{float(p["lat"])}' for p in points)
    src=";".join(str(i) for i in range(len(origins)))
    dst=";".join(str(i) for i in range(len(origins),len(points)))
    url=f"{OSRM_API_BASE}/table/v1/driving/{coords}"
    r=SESSION.get(url,params={"annotations":"distance,duration","sources":src,"destinations":dst},timeout=30); r.raise_for_status()
    data=r.json(); rows=[]
    for oi,row in enumerate(data.get("distances") or []):
        for di,distance in enumerate(row):
            duration=(data.get("durations") or [[]])[oi][di]
            rows.append({"origin_index":oi,"destination_index":di,"distance_km":round(distance/1000,2) if distance is not None else None,"duration_min":round(duration/60,1) if duration is not None else None,"ok":distance is not None and duration is not None})
    return rows

def route_matrix(points):
    out=[]
    for origin,destination in points: out.extend(route_matrix_batch([origin],[destination]))
    return out

def decode_polyline(poly):
    coords=[]; index=0; lat=lng=0
    while index<len(poly):
        result=shift=0
        while True:
            b=ord(poly[index])-63; index+=1; result|=(b&31)<<shift; shift+=5
            if b<32: break
        lat += ~(result>>1) if result&1 else result>>1
        result=shift=0
        while True:
            b=ord(poly[index])-63; index+=1; result|=(b&31)<<shift; shift+=5
            if b<32: break
        lng += ~(result>>1) if result&1 else result>>1
        coords.append((lat/1e5,lng/1e5))
    return coords

def sample_polyline(poly,n=5):
    pts=decode_polyline(poly) if poly else []
    if not pts:return []
    if len(pts)<=n:return [{"lat":a,"lng":b} for a,b in pts]
    idxs=[round(i*(len(pts)-1)/(n-1)) for i in range(n)]
    return [{"lat":pts[i][0],"lng":pts[i][1]} for i in idxs]

def stable_int(key,low,high):
    h=hashlib.sha256(key.encode()).hexdigest(); return low+int(h[:8],16)%(high-low+1)
def simulated_queue(station_id,connectors):
    bucket=int(time.time()//300); return max(0,stable_int(f"{station_id}-{bucket}",0,max(1,connectors*2)))

def normalize_vehicle(vehicle,personal_range_km=None):
    official=vehicle["reference_range_km"]
    if personal_range_km: blended=.60*official+.40*personal_range_km; source="60% manufacturer/official reference + 40% owner estimate"
    else: blended=official; source="manufacturer/official reference only"
    out=dict(vehicle); out["effective_range_km"]=round(blended,1); out["effective_km_per_kwh"]=round(blended/vehicle["battery_kwh"],3); out["effective_kwh_per_100km"]=round(vehicle["battery_kwh"]/blended*100,2); out["range_blend_source"]=source
    return out

def usable_range(vehicle,battery_pct,personal_range_km=None):
    v=normalize_vehicle(vehicle,personal_range_km); return max(0,(battery_pct-v["reserve_pct"])/100*v["effective_range_km"])
def charging_minutes(vehicle,start_pct,target_pct,charger_kw):
    if target_pct<=start_pct:return 0
    target=min(target_pct,90); energy=vehicle["battery_kwh"]*(target-start_pct)/100; power=max(1,min(charger_kw,vehicle["dc_kw"])); taper=1+max(0,target-70)*.012
    return energy/power*60*1.12*taper

def _bee_to_station(x):
    lat=x.get("latitude"); lng=x.get("longitude")
    if not _in_india(lat,lng): return None
    ports=[]; max_power=float(x.get("max_power_kw") or 0)
    for charger in x.get("chargers") or []:
        for gun in charger.get("guns") or []:
            ports.append({"type":gun.get("standard") or charger.get("type_raw") or "Not reported","power_kw":gun.get("kw"),"quantity":1})
    if not ports:
        for standard in x.get("standards") or []: ports.append({"type":standard,"power_kw":max_power or None,"quantity":1})
    return {"id":str(x.get("id")),"name":x.get("city") or x.get("address") or "EV charging station","lat":float(lat),"lng":float(lng),"address":x.get("address") or ", ".join(v for v in [x.get("city"),x.get("district"),x.get("state")] if v),"operator":x.get("operator") or "Not reported","status":"Not reported by BEE dataset","status_is_operational":None,"usage":"Public charging station (BEE dataset)","usage_cost":"Pricing not reported","ports":ports,"max_power_kw":max_power or None,"source":"BEE India dataset (26 Oct 2025)","ocm_url":None,"map_url":None,"distance_km":x.get("distance_km"),"standards":x.get("standards") or [],"state":x.get("state"),"district":x.get("district"),"city":x.get("city")}

def fetch_bee_near(lat,lng,distance_km=25,maxresults=50):
    if not _in_india(lat,lng): return []
    r=SESSION.get(f"{BEE_API_BASE}/v1/stations/near",params={"lat":lat,"lng":lng,"radius":min(100,max(.1,distance_km)),"limit":min(100,max(1,maxresults))},timeout=20); r.raise_for_status()
    data=r.json()
    return [s for s in (_bee_to_station(x) for x in (data.get("data") or [])) if s]

def fetch_overpass_near(lat,lng,distance_km=25,maxresults=60):
    """OpenStreetMap fallback; directory records, not guaranteed live charger availability."""
    radius_m=int(min(100,max(.5,distance_km))*1000)
    query=f"""[out:json][timeout:20];(node(around:{radius_m},{lat},{lng})[amenity=charging_station];way(around:{radius_m},{lat},{lng})[amenity=charging_station];relation(around:{radius_m},{lat},{lng})[amenity=charging_station];);out center tags;"""
    r=SESSION.post("https://overpass-api.de/api/interpreter",data={"data":query},timeout=28); r.raise_for_status()
    out=[]
    for x in r.json().get("elements",[])[:maxresults]:
        tags=x.get("tags") or {}; center=x.get("center") or {}
        la=x.get("lat",center.get("lat")); lo=x.get("lon",center.get("lon"))
        if not _in_india(la,lo): continue
        power=None
        try: power=float(str(tags.get("socket:output") or tags.get("maxpower") or "").lower().replace("kw","").strip())
        except Exception: pass
        plugs=[{"type":k.replace("socket:","").replace("_"," ").upper(),"power_kw":power,"quantity":1} for k,v in tags.items() if k.startswith("socket:") and v not in ("no","0")]
        out.append({"id":f"osm:{x.get('type')}:{x.get('id')}","name":tags.get("name") or tags.get("operator") or "EV charging station","lat":float(la),"lng":float(lo),"address":", ".join(v for v in [tags.get("addr:street"),tags.get("addr:city"),tags.get("addr:state")] if v) or "Address not reported","operator":tags.get("operator") or "Not reported","status":"Not reported","status_is_operational":None,"usage":"Public charging station (OpenStreetMap)","usage_cost":"Pricing not reported","ports":plugs,"max_power_kw":power,"source":"OpenStreetMap / Overpass","ocm_url":None,"map_url":f"https://www.openstreetmap.org/{x.get('type')}/{x.get('id')}"})
    return out

def fill_demo_station_fields(station):
    """Fill gaps deterministically so demo results are stable within a 5-minute window."""
    seed=f"{station.get('id','station')}-{int(time.time()//300)}"
    if not station.get("ports"):
        n=stable_int(seed+"-ports",1,3)
        station["ports"]=[{"type":t,"power_kw":kw,"quantity":1} for t,kw in zip(["CCS2 DC","Type 2 AC","Bharat DC-001"],[30,7.2,15])][:n]
    if not station.get("max_power_kw"):
        station["max_power_kw"]=max((p.get("power_kw") or 0 for p in station["ports"]),default=0) or [7.2,30,50,60][stable_int(seed+"-power",0,3)]
    if station.get("status_is_operational") is None:
        operational=stable_int(seed+"-status",0,9)>1
        station["status_is_operational"]=operational
        station["status"]="Demo: likely available" if operational else "Demo: temporarily unavailable"
        station["status_simulated"]=True
    elif not station.get("status"):
        station["status"]="Reported operational" if station["status_is_operational"] else "Reported unavailable"
    if not station.get("usage_cost") or station["usage_cost"]=="Pricing not reported":
        station["usage_cost"]=f"₹{stable_int(seed+'-price',12,24)} / kWh (simulated)"
        station["price_simulated"]=True
    connectors=max(1,sum(int(p.get("quantity") or 1) for p in station["ports"]))
    station["queue"]=stable_int(seed+"-queue",0,max(2,connectors*2))
    station["estimated_wait_min"]=station["queue"]*7
    station["queue_simulated"]=True
    station["wait_simulated"]=True
    return station

def fetch_ocm_near(lat,lng,distance_km=25,maxresults=30):
    if not OCM_KEY or not _in_india(lat,lng): return []
    params={"output":"json","latitude":lat,"longitude":lng,"distance":distance_km,"distanceunit":"KM","maxresults":maxresults,"compact":"false","verbose":"true","key":OCM_KEY}
    r=SESSION.get("https://api.openchargemap.io/v3/poi/",params=params,headers={"X-API-Key":OCM_KEY},timeout=20); r.raise_for_status()
    out=[]
    for x in r.json() or []:
        a=x.get("AddressInfo") or {}; la=a.get("Latitude"); lo=a.get("Longitude")
        if not _in_india(la,lo): continue
        connections=x.get("Connections") or []; ports=[]; power=0
        for c in connections:
            conn=c.get("ConnectionType") or {}; kw=c.get("PowerKW")
            if kw: power=max(power,float(kw))
            ports.append({"type":conn.get("Title") or "Not reported","power_kw":kw,"quantity":1})
        status=x.get("StatusType") or {}
        out.append({"id":f"ocm:{x.get('ID')}","name":a.get("Title") or "EV charging station","lat":float(la),"lng":float(lo),"address":a.get("AddressLine1") or a.get("Title") or "Address not reported","operator":((x.get("OperatorInfo") or {}).get("Title") or "Not reported"),"status":status.get("Title") or "Not reported","status_is_operational":status.get("IsOperational"),"usage":((x.get("UsageType") or {}).get("Title") or "Not reported"),"usage_cost":((x.get("UsageCost") or "Pricing not reported")),"ports":ports,"max_power_kw":power or None,"source":"Open Charge Map","ocm_url":f"https://openchargemap.org/site/poi/{x.get('ID')}","map_url":None})
    return out

def merge_stations(groups):
    merged={}
    for group in groups:
        for s in group:
            key=(round(float(s.get("lat") or 0),4),round(float(s.get("lng") or 0),4),str(s.get("name") or "").lower()[:30])
            if key not in merged: merged[key]=s
            else:
                old=merged[key]
                if not old.get("ports") and s.get("ports"): old["ports"]=s["ports"]
                if old.get("status_is_operational") is None: old["status_is_operational"]=s.get("status_is_operational")
                if old.get("operator") in (None,"Not reported"): old["operator"]=s.get("operator")
                if old.get("source") and s.get("source") and s["source"] not in old["source"]: old["source"] += " + "+s["source"]
    return list(merged.values())

def autocomplete_places(text):
    params={"q":text,"limit":7,"lang":"en","bbox":"67,6,99,38"}
    r=SESSION.get(f"{PHOTON_API_BASE}/api/",params=params,timeout=12); r.raise_for_status()
    suggestions=[]
    for f in r.json().get("features") or []:
        c=(f.get("geometry") or {}).get("coordinates") or []
        if len(c)<2 or not _in_india(c[1],c[0]): continue
        p=f.get("properties") or {}; name=p.get("name") or p.get("street") or p.get("city") or "Indian location"
        secondary=", ".join(str(p[k]) for k in ("district","city","state","country") if p.get(k))
        suggestions.append({"place_id":f'{c[1]},{c[0]}',"text":", ".join(x for x in [name,secondary] if x),"main_text":name,"secondary_text":secondary})
    return suggestions

def place_details(place_id):
    try: lat,lng=[float(v) for v in place_id.split(",",1)]
    except Exception: raise ValueError("Invalid location selection")
    if not _in_india(lat,lng): raise ValueError("Only Indian locations are supported")
    return {"place_id":place_id,"formatted":f"{lat:.5f}, {lng:.5f}","lat":lat,"lng":lng}

# Compatibility names retained for callers from earlier releases; Google services are removed.
def search_ev_stations_along_route(polyline,source,max_results=20):
    groups=[fetch_bee_near(p["lat"],p["lng"],20,100) for p in sample_polyline(polyline,8)]
    if OCM_KEY:
        groups += [fetch_ocm_near(p["lat"],p["lng"],15,60) for p in sample_polyline(polyline,5)]
    return merge_stations(groups)[:max_results]
def search_ev_stations_nearby_google(lat,lng,max_results=20): return fetch_bee_near(lat,lng,30,max_results)
def enrich_google_stations_with_ocm(stations,radius_km=2): return stations
