from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
import hashlib, secrets, time, requests
from fastapi.staticfiles import StaticFiles
from .config import CORS_ORIGINS, OPENCHARGEMAP_API_KEY, EV_ADMIN_TOKEN, BEE_API_BASE, RESEND_API_KEY, EMAIL_FROM, VEHICLE_INGEST_TOKEN
from .data import VEHICLES, vehicle_with_defaults
from .models import ProfileIn, PurchaseIn, PlanIn
from .db import init_db, upsert_owner, get_owner, add_purchase, add_route, list_owners, list_purchases, list_routes, delete_owner, delete_purchase, clear_all, save_otp, check_otp, email_verified, save_telemetry, get_telemetry
from .services import geocode, compute_route, sample_polyline, fetch_bee_near, fetch_ocm_near, fetch_overpass_near, fill_demo_station_fields, merge_stations, normalize_vehicle, usable_range, charging_minutes, simulated_queue, route_matrix_batch, autocomplete_places, place_details

app=FastAPI(title="EVChargeRoute India API",version="5.0.0")
app.add_middleware(CORSMiddleware,allow_origins=CORS_ORIGINS,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
@app.on_event("startup")
def startup(): init_db()
def admin_guard(x_admin_token:str=Header(default="")):
    if not EV_ADMIN_TOKEN or x_admin_token!=EV_ADMIN_TOKEN: raise HTTPException(401,"Invalid admin token")
    return True
@app.get("/api/health")
def health(): return {"status":"ok","google_removed":True,"india_station_api":"BEE-derived public directory","openchargemap_configured":bool(OPENCHARGEMAP_API_KEY),"routing":"OSRM","geocoding":"Photon","map_tiles":"OpenFreeMap"}
@app.get("/api/vehicles")
def vehicles(): return {k:vehicle_with_defaults(v) for k,v in VEHICLES.items()}
class OTPRequest(BaseModel):
    email: str = Field(min_length=5,max_length=180)
class OTPVerify(BaseModel):
    email: str = Field(min_length=5,max_length=180)
    otp: str = Field(min_length=6,max_length=6)
class TelemetryIn(BaseModel):
    email: str = Field(min_length=5,max_length=180)
    battery_pct: Optional[float] = Field(default=None,ge=0,le=100)
    range_km: Optional[float] = Field(default=None,ge=0,le=3000)
    odometer_km: Optional[float] = Field(default=None,ge=0,le=3000000)
    lat: Optional[float] = Field(default=None,ge=6,le=38)
    lng: Optional[float] = Field(default=None,ge=67,le=99)
    speed_kmh: Optional[float] = Field(default=None,ge=0,le=500)


@app.post("/api/auth/request-otp")
def request_otp(req: OTPRequest):
    if not RESEND_API_KEY or not EMAIL_FROM:
        raise HTTPException(
            503,
            "Email OTP is not configured. Set RESEND_API_KEY and EMAIL_FROM in Render."
        )

    otp = f"{secrets.randbelow(1000000):06d}"

    payload = {
        "from": EMAIL_FROM,
        "to": [req.email],
        "subject": "Your EVChargeRoute verification code",
        "text": (
            f"Your EVChargeRoute verification code is {otp}. "
            "It expires in 10 minutes. If you did not request it, ignore this email."
        ),
        "html": (
            f"<h2>EVChargeRoute Email Verification</h2>"
            f"<p>Your verification code is:</p>"
            f"<h1>{otp}</h1>"
            f"<p>This code expires in 10 minutes.</p>"
            f"<p>If you did not request it, ignore this email.</p>"
        )
    }

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=20
        )

        if response.status_code >= 400:
            raise HTTPException(
                502,
                f"Email provider error ({response.status_code}): {response.text[:300]}"
            )

        # Save the OTP only after the email provider accepts the request.
        save_otp(
            req.email,
            hashlib.sha256(
                (req.email.lower() + otp).encode()
            ).hexdigest(),
            time.time() + 600
        )

    except requests.RequestException:
        raise HTTPException(
            502,
            "Could not connect to the email provider. Please try again."
        )

    return {"sent": True, "expires_in_seconds": 600}


@app.post("/api/auth/verify-otp")
def verify_otp(req:OTPVerify):
    digest=hashlib.sha256((req.email.lower()+req.otp).encode()).hexdigest()
    if not check_otp(req.email,digest,time.time()): raise HTTPException(400,"Invalid or expired OTP. Request a new code and try again.")
    return {"verified":True,"email":req.email.lower(),"valid_for_seconds":86400}
@app.get("/api/telemetry")
def telemetry(email:str=Query(min_length=5,max_length=180)):
    if not email_verified(email,time.time()): raise HTTPException(403,"Verify your email first")
    return {"telemetry":get_telemetry(email)}
@app.post("/api/telemetry/ingest")
def ingest_telemetry(req:TelemetryIn,x_vehicle_token:str=Header(default="")):
    if not VEHICLE_INGEST_TOKEN or not secrets.compare_digest(x_vehicle_token,VEHICLE_INGEST_TOKEN):
        raise HTTPException(401,"Invalid vehicle telemetry integration token")
    save_telemetry(req.email,req.model_dump(exclude={"email"}))
    return {"accepted":True,"updated":True}

@app.post("/api/profile")
def save_profile(req: ProfileIn):
    # Validate the selected vehicle.
    if req.vehicle_id not in VEHICLES:
        raise HTTPException(400, "Unknown vehicle model")

    # Check whether this email already belongs to a saved profile.
    existing_owner = get_owner(email=req.email)

    # OTP is optional for a brand-new profile.
    # However, OTP is required before an existing profile can be updated.
    if existing_owner and not email_verified(req.email, time.time()):
        raise HTTPException(
            status_code=403,
            detail="This email already has a saved profile. Verify your email with OTP before updating it."
        )

    return upsert_owner(req.model_dump())

@app.get("/api/profile")
def load_profile(email:str=Query(min_length=3,max_length=180)):
    if not email_verified(email,time.time()): raise HTTPException(403,"Verify this email address with the OTP before loading a profile")
    owner=get_owner(email=email)
    if not owner: raise HTTPException(404,"No saved owner profile found for that email")
    return owner
@app.post("/api/purchases")
def purchase(req:PurchaseIn):
    if not get_owner(owner_id=req.owner_id): raise HTTPException(404,"Owner profile not found")
    return add_purchase(req.model_dump())
@app.get("/api/places/autocomplete")
def places_autocomplete(input:str=Query(min_length=2,max_length=300)):
    try:return {"suggestions":autocomplete_places(input)}
    except Exception as e:raise HTTPException(502,f"India location search error: {e}")
@app.get("/api/places/{place_id}")
def places_details(place_id:str):
    try:return place_details(place_id)
    except Exception as e:raise HTTPException(400,f"Location details error: {e}")
@app.get("/api/stations")
def stations(lat:float,lng:float,distance_km:float=30):
    if not (6<=lat<=38 and 67<=lng<=99): raise HTTPException(400,"Only locations within India are supported")
    groups=[]; errors=[]
    try: groups.append(fetch_bee_near(lat,lng,min(distance_km,100),100))
    except Exception as e: errors.append(f"India BEE dataset: {e}")
    if OPENCHARGEMAP_API_KEY:
        try: groups.append(fetch_ocm_near(lat,lng,min(distance_km,100),100))
        except Exception as e: errors.append(f"Open Charge Map: {e}")
    try: groups.append(fetch_overpass_near(lat,lng,min(distance_km,100),100))
    except Exception as e: errors.append(f"OpenStreetMap fallback: {e}")
    data=merge_stations(groups)
    data=[fill_demo_station_fields(s) for s in data]
    if not data and errors: raise HTTPException(502,"Station provider error: "+" | ".join(errors))
    return {"live":False,"directory_data_available":bool(data),"stations":data,"count":len(data),"source":"BEE India dataset"+(" + Open Charge Map" if OPENCHARGEMAP_API_KEY else ""),"message":"; ".join(errors) if errors else None,"attribution":"BEE, Ministry of Power, Government of India — EV Public Charging Stations Data till 26 October 2025. Republished dataset; not an official BEE service."}
@app.post("/api/plan")
def plan(req:PlanIn):
    if req.vehicle_id not in VEHICLES: raise HTTPException(400,"Unknown vehicle model")
    try:
        vehicle=normalize_vehicle(VEHICLES[req.vehicle_id],req.personal_range_km)
        source=geocode(req.source); destination=geocode(req.destination)
        route=compute_route(source,destination,traffic=False)
    except Exception as e: raise HTTPException(502,f"India route provider error: {e}")
    safe_range=usable_range(VEHICLES[req.vehicle_id],req.battery_pct,req.personal_range_km); direct=safe_range>=route["distance_km"]
    groups=[]
    for point in sample_polyline(route["polyline"],8):
        try: groups.append(fetch_bee_near(point["lat"],point["lng"],20,100))
        except Exception: pass
        if OPENCHARGEMAP_API_KEY:
            try: groups.append(fetch_ocm_near(point["lat"],point["lng"],15,50))
            except Exception: pass
    live_stations=merge_stations(groups)
    if not live_stations:
        for point in sample_polyline(route["polyline"],4):
            try: groups.append(fetch_overpass_near(point["lat"],point["lng"],15,60))
            except Exception: pass
        live_stations=merge_stations(groups)
    valid=[s for s in live_stations if s.get("lat") is not None and s.get("lng") is not None]
    valid=valid[:45]; points=[{"lat":s["lat"],"lng":s["lng"]} for s in valid]
    candidates=[]
    if points:
        try:
            source_legs=route_matrix_batch([source],points)
            destination_legs=route_matrix_batch(points,[destination])
        except Exception as e: raise HTTPException(502,f"OSRM route matrix error: {e}")
        by_dest={r["destination_index"]:r for r in source_legs if r.get("destination_index") is not None}
        by_origin={r["origin_index"]:r for r in destination_legs if r.get("origin_index") is not None}
        for idx,s in enumerate(valid):
            s=fill_demo_station_fields(s)
            to_s=by_dest.get(idx); from_s=by_origin.get(idx)
            if not to_s or not from_s or not to_s["ok"] or not from_s["ok"]: continue
            reachable=to_s["distance_km"]<=safe_range
            connectors=max(1,len(s.get("ports") or [])); queue=simulated_queue(s["id"],connectors); wait=queue*7
            energy=to_s["distance_km"]*vehicle["battery_kwh"]/vehicle["effective_range_km"]
            station_soc=max(0,req.battery_pct-energy/vehicle["battery_kwh"]*100)
            target=min(90,max(station_soc,from_s["distance_km"]/vehicle["effective_range_km"]*100+vehicle["reserve_pct"]))
            charge=charging_minutes(vehicle,station_soc,target,s.get("max_power_kw") or 50)
            detour=max(0,to_s["distance_km"]+from_s["distance_km"]-route["distance_km"])
            drive=max(0,to_s["duration_min"]+from_s["duration_min"]-route["duration_min"])
            extra=round(wait+charge+drive,1) if reachable else None
            row=dict(s); row.update({"distance_from_source_km":to_s["distance_km"],"station_to_destination_km":from_s["distance_km"],"detour_km":round(detour,2),"queue":queue,"estimated_wait_min":wait,"station_soc_pct":round(station_soc,1),"target_soc_pct":round(target,1),"estimated_charge_min":round(charge,1) if reachable else None,"total_extra_min":extra,"reachable":reachable,"score":extra if reachable else None})
            candidates.append(row)
    candidates.sort(key=lambda x:x["score"] if x["score"] is not None else float("inf"))
    recommendation=candidates[0] if candidates and candidates[0]["reachable"] else None
    if direct: decision="DIRECT"; message="Your EV can reach the destination while retaining its configured safety reserve."
    elif recommendation: decision="CHARGE"; message="A listed charging station is reachable. Stops are ranked using road distance, estimated charging time and a simulated queue."
    else: decision="WARNING"; message="No reachable station was found in the available directory data. Verify coverage and charger details before travelling."
    result={"decision":decision,"message":message,"vehicle":vehicle,"origin":source,"destination":destination,"route":route,"distance_km":route["distance_km"],"duration_min":route["duration_min"],"available_range_km":round(safe_range,1),"battery_pct":req.battery_pct,"recommended_station":recommendation,"stations":candidates[:20],"subscription":req.subscription,"queue_note":"Queue count is simulated, not live. The BEE snapshot does not provide real-time availability, prices or opening hours. Provider-reported fields are shown when available.","formula":"OSRM road route + BEE India station directory + optional Open Charge Map enrichment + personalized EV range model + simulated queue + estimated charge time","provider_note":None}
    add_route({"owner_id":req.owner_id,"source":req.source,"destination":req.destination,"vehicle_id":req.vehicle_id,"distance_km":route["distance_km"],"duration_min":route["duration_min"],"decision":decision})
    return result
@app.get("/api/admin/owners")
def admin_owners(_:bool=Depends(admin_guard)):return list_owners()
@app.get("/api/admin/purchases")
def admin_purchases(_:bool=Depends(admin_guard)):return list_purchases()
@app.get("/api/admin/routes")
def admin_routes(_:bool=Depends(admin_guard)):return list_routes()
@app.delete("/api/admin/owners/{owner_id}")
def admin_delete_owner(owner_id:int,_:bool=Depends(admin_guard)):
    if not delete_owner(owner_id):raise HTTPException(404,"Owner not found")
    return {"deleted":True}
@app.delete("/api/admin/purchases/{purchase_id}")
def admin_delete_purchase(purchase_id:int,_:bool=Depends(admin_guard)):
    if not delete_purchase(purchase_id):raise HTTPException(404,"Purchase not found")
    return {"deleted":True}
@app.delete("/api/admin/all")
def admin_clear_all(_:bool=Depends(admin_guard)):clear_all();return {"deleted":True}
DIST=__import__("pathlib").Path(__file__).resolve().parents[2]/"frontend"/"dist"
if DIST.exists():
    app.mount("/assets",StaticFiles(directory=DIST/"assets"),name="assets")
    @app.get("/{path:path}")
    def serve_react(path:str):
        p=DIST/path
        if path and p.exists() and p.is_file():return FileResponse(p)
        return FileResponse(DIST/"index.html")
