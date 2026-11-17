import React,{useEffect,useRef,useState} from "react";
import {Card,Alert} from "react-bootstrap";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export default function MapView({result}){
 const ref=useRef(null); const mapRef=useRef(null); const [msg,setMsg]=useState("");
 useEffect(()=>{
  if(!ref.current||!result)return; let map;
  try{
   const origin=result.origin,dest=result.destination;
   map=new maplibregl.Map({container:ref.current,style:"https://tiles.openfreemap.org/styles/liberty",center:[origin.lng,origin.lat],zoom:6});
   mapRef.current=map; map.addControl(new maplibregl.NavigationControl(),"top-right");
   map.on("load",()=>{
    const features=[]; const add=(coords,properties={})=>features.push({type:"Feature",geometry:{type:"Point",coordinates:coords},properties});
    add([origin.lng,origin.lat],{label:"A · Origin"}); add([dest.lng,dest.lat],{label:"B · Destination"});
    (result.stations||[]).forEach(s=>{if(s.lat!=null&&s.lng!=null)add([Number(s.lng),Number(s.lat)],{label:s.name||"Charging station",operator:s.operator||"Not reported",status:s.status||"Not reported"})});
    const path=decode(result.route?.polyline||"");
    map.addSource("route-line",{type:"geojson",data:{type:"Feature",geometry:{type:"LineString",coordinates:path.map(p=>[p.lng,p.lat])},properties:{}}});
    map.addLayer({id:"route-line",type:"line",source:"route-line",paint:{"line-color":"#2563eb","line-width":5,"line-opacity":.85}});
    map.addSource("places",{type:"geojson",data:{type:"FeatureCollection",features}});
    map.addLayer({id:"places",type:"circle",source:"places",paint:{"circle-radius":7,"circle-color":["case",["==",["get","label"],"A · Origin"],"#16a34a",["==",["get","label"],"B · Destination"],"#dc2626","#f59e0b"],"circle-stroke-width":2,"circle-stroke-color":"#ffffff"}});
    map.on("click","places",e=>{const p=e.features?.[0]?.properties||{};new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<strong>${escapeHtml(p.label||"Location")}</strong><br>${escapeHtml(p.operator||"")}<br>${escapeHtml(p.status||"")}`).addTo(map)});
    map.on("mouseenter","places",()=>map.getCanvas().style.cursor="pointer"); map.on("mouseleave","places",()=>map.getCanvas().style.cursor="");
    const bounds=new maplibregl.LngLatBounds([origin.lng,origin.lat],[dest.lng,dest.lat]);
    (result.stations||[]).forEach(s=>{if(s.lat!=null&&s.lng!=null)bounds.extend([Number(s.lng),Number(s.lat)])});
    path.forEach(p=>bounds.extend([p.lng,p.lat])); map.fitBounds(bounds,{padding:55,maxZoom:12});
   });
   map.on("error",e=>setMsg(e.error?.message||"Map tiles could not be loaded. Check your internet connection."));
  }catch(e){setMsg(e.message||"Map could not be initialized.")}
  return()=>{map?.remove();mapRef.current=null};
 },[result]);
 return <Card className="shadow-sm border-0 mt-4"><Card.Body className="p-2">{msg&&<Alert className="m-2" variant="warning">{msg}</Alert>}<div ref={ref} className="map-box" style={{minHeight:420,borderRadius:10,overflow:"hidden"}}/></Card.Body></Card>
}
function escapeHtml(v){return String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
function decode(str){const pts=[];let i=0,lat=0,lng=0;while(i<str.length){let r=0,s=0,b;do{b=str.charCodeAt(i++)-63;r|=(b&31)<<s;s+=5}while(b>=32);lat+=(r&1)?~(r>>1):(r>>1);r=0;s=0;do{b=str.charCodeAt(i++)-63;r|=(b&31)<<s;s+=5}while(b>=32);lng+=(r&1)?~(r>>1):(r>>1);pts.push({lat:lat/1e5,lng:lng/1e5})}return pts;}
