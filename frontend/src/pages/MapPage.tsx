import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, CircleMarker, useMap, FeatureGroup } from 'react-leaflet';
import { EditControl } from 'react-leaflet-draw';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { useHouseholdStore } from '../stores/household.store';
import { useUiStore } from '../stores/ui.store';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import { ShieldAlert, Home, Info, Layers, Zap, MapPin, Activity, PencilRuler } from 'lucide-react';
import { cn } from '../lib/utils';
import { toast } from 'react-hot-toast';

// Fix for Leaflet default marker icons
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});
L.Marker.prototype.options.icon = DefaultIcon;

function MapResizer() {
  const map = useMap();
  useEffect(() => {
    setTimeout(() => {
      map.invalidateSize();
    }, 250);
  }, [map]);
  return null;
}

export function MapPage() {
  const { households } = useHouseholdStore();
  const { openPanel, emergencyMode } = useUiStore();
  const [viewMode, setViewMode] = useState<'standard' | 'heat' | 'clusters'>('clusters');

  // Mumbai Center
  const position: [number, number] = [19.0330, 72.8634];

  const getUrgencyColor = (score: number) => {
    if (score > 0.85) return '#ef4444'; // Red-500
    if (score > 0.6) return '#f97316';  // Orange-500
    if (score > 0.4) return '#eab308';  // Yellow-500
    return '#22c55e'; // Green-500
  };

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900 leading-tight">Operations Command Map</h2>
          <p className="text-sm text-gray-500 mt-1">Real-time geospatial logic for disaster response and volunteer dispatch.</p>
        </div>
        
        <div className="flex bg-white p-1 rounded-2xl border border-warm-border shadow-sm">
          <div className="hidden lg:flex items-center px-4 border-r border-slate-100 mr-1">
             <div className="flex items-center gap-2">
                <PencilRuler className="w-3.5 h-3.5 text-brand-400" />
                <span className="text-[9px] font-black uppercase text-gray-400 tracking-tighter">Geo-Fencing Active</span>
             </div>
          </div>
          <button 
            onClick={() => setViewMode('clusters')}
            className={cn(
              "px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2",
              viewMode === 'clusters' ? "bg-brand-600 text-white shadow-lg shadow-brand-200" : "text-gray-500 hover:bg-slate-50"
            )}
          >
            <Layers className="w-3.5 h-3.5" /> Clusters
          </button>
          <button 
            onClick={() => setViewMode('heat')}
            className={cn(
              "px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2",
              viewMode === 'heat' ? "bg-brand-600 text-white shadow-lg shadow-brand-200" : "text-gray-500 hover:bg-slate-50"
            )}
          >
            <Activity className="w-3.5 h-3.5" /> Vuln Heat
          </button>
        </div>
      </div>

      <div className={cn(
        "flex-1 rounded-[40px] overflow-hidden border-2 border-warm-border shadow-2xl relative min-h-[500px] bg-slate-100",
        emergencyMode && "border-4 border-black rounded-none shadow-none"
      )}>
        <MapContainer 
          center={position} 
          zoom={13} 
          scrollWheelZoom={true}
          className="h-full w-full z-0"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          <MapResizer />

          <FeatureGroup>
            <EditControl
              position="topleft"
              onCreated={(e) => {
                const { layerType } = e;
                if (layerType === 'polygon') {
                  toast.success('Assigned neighborhood zone successfully', {
                    icon: '📍',
                    style: { borderRadius: '16px', background: '#312e81', color: '#fff', fontSize: '12px', fontWeight: 'bold' }
                  });
                }
              }}
              draw={{
                rectangle: false,
                circle: false,
                polyline: false,
                circlemarker: false,
                marker: false,
                polygon: {
                  allowIntersection: false,
                  drawError: {
                    color: '#e1e1e1',
                    message: '<strong>Error:</strong> Polygon edges cannot cross!'
                  },
                  shapeOptions: {
                    color: '#4f46e5',
                    fillOpacity: 0.2
                  }
                }
              }}
            />
          </FeatureGroup>

          {viewMode === 'clusters' && (
            <MarkerClusterGroup
              chunkedLoading
              maxClusterRadius={50}
            >
              {households.map((hh) => (
                <Marker 
                  key={hh.hh_id} 
                  position={[hh.lat, hh.lng]}
                >
                  <Popup className="nexus-map-popup">
                    <div className="w-48">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] px-2 py-0.5 bg-brand-50 text-brand-700 font-bold rounded-full">
                          {hh.hh_id}
                        </span>
                        <div 
                          className="w-2 h-2 rounded-full animate-pulse" 
                          style={{ backgroundColor: getUrgencyColor(hh.vuln_score) }}
                        />
                      </div>
                      <h4 className="text-xs font-bold text-slate-900 mb-1">{hh.location_desc}</h4>
                      <p className="text-[10px] text-gray-500 mb-3">{hh.members} Members • {hh.status}</p>
                      
                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
                        <div className="flex flex-col">
                          <span className="text-[9px] uppercase font-bold text-gray-400">Risk</span>
                          <span className="text-xs font-black" style={{ color: getUrgencyColor(hh.vuln_score) }}>
                            {(hh.vuln_score * 100).toFixed(0)}%
                          </span>
                        </div>
                        <button 
                          onClick={() => openPanel('household_details', hh.hh_id)}
                          className="bg-brand-600 text-white px-3 py-1.5 rounded-lg text-[10px] font-bold hover:bg-brand-900 transition-all shadow-sm"
                        >
                          Triage
                        </button>
                      </div>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MarkerClusterGroup>
          )}

          {viewMode === 'heat' && (
            <>
              {households.map((hh) => (
                <CircleMarker
                  key={`heat-dot-${hh.hh_id}`}
                  center={[hh.lat, hh.lng]}
                  radius={15 + (hh.vuln_score * 40)}
                  fillColor={getUrgencyColor(hh.vuln_score)}
                  color="transparent"
                  fillOpacity={0.4}
                >
                  <Popup>
                    <div className="text-center">
                      <p className="text-[10px] font-black uppercase text-gray-400">Risk Density</p>
                      <p className="text-lg font-black" style={{ color: getUrgencyColor(hh.vuln_score) }}>
                        {(hh.vuln_score * 100).toFixed(0)}
                      </p>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </>
          )}
        </MapContainer>

        {/* Legend Overlay */}
        <div className="absolute top-6 right-6 z-[1000] bg-white/90 backdrop-blur p-4 rounded-3xl border border-warm-border shadow-xl min-w-[160px]">
          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
            <ShieldAlert className="w-3 h-3 text-brand-600" /> Assessment Key
          </h4>
          <div className="space-y-4">
            <div className="group flex items-center justify-between cursor-help">
              <span className="text-[11px] font-bold text-slate-600 group-hover:text-red-600 transition-colors">Critical</span>
              <div className="w-8 h-2 rounded-full bg-red-500 shadow-sm shadow-red-200"></div>
            </div>
            <div className="group flex items-center justify-between cursor-help">
              <span className="text-[11px] font-bold text-slate-600 group-hover:text-orange-500 transition-colors">High Risk</span>
              <div className="w-8 h-2 rounded-full bg-orange-500 shadow-sm shadow-orange-100"></div>
            </div>
            <div className="group flex items-center justify-between cursor-help">
              <span className="text-[11px] font-bold text-slate-600 group-hover:text-green-600 transition-colors">Stable</span>
              <div className="w-8 h-2 rounded-full bg-green-500 shadow-sm shadow-green-100"></div>
            </div>
          </div>
          
          <div className="mt-6 pt-4 border-t border-slate-100">
             <div className="flex flex-col items-center justify-center p-2 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-tighter">Current Zone</span>
                <span className="text-[10px] font-black text-brand-900 tracking-tight">MUMBAI DISTRICT</span>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
