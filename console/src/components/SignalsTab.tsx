import React, { useState, useRef } from 'react';
import { Zap, Gauge, BatteryCharging, Power, Thermometer, ShieldAlert, CheckCircle2, History } from 'lucide-react';
import { FleetInstance, api } from '../api';

interface SignalsTabProps {
  instances: FleetInstance[];
  selectedInstanceId: string | null;
  setSelectedInstanceId: (id: string) => void;
}

interface InjectionLog {
  id: string;
  time: string;
  signal: string;
  value: any;
  latency_ms: number;
  propName: string;
}

export const SignalsTab: React.FC<SignalsTabProps> = ({
  instances,
  selectedInstanceId,
  setSelectedInstanceId,
}) => {
  const onlineInstances = instances.filter((i) => i.status === 'ONLINE');
  const activeInst = onlineInstances.find((i) => i.instance_id === selectedInstanceId) || onlineInstances[0];

  // Local signal states
  const [currentGear, setCurrentGear] = useState<'PARK' | 'REVERSE' | 'NEUTRAL' | 'DRIVE'>('PARK');
  const [speedKmh, setSpeedKmh] = useState<number>(0);
  const [ignition, setIgnition] = useState<'OFF' | 'ACC' | 'ON' | 'START'>('ON');
  const [batterySoc, setBatterySoc] = useState<number>(80);
  const [chargePortOpen, setChargePortOpen] = useState<boolean>(false);
  const [cableConnected, setCableConnected] = useState<boolean>(false);
  const [parkingBrakeOn, setParkingBrakeOn] = useState<boolean>(true);
  const [hvacTemp, setHvacTemp] = useState<number>(21.5);

  const [loadingSignal, setLoadingSignal] = useState<string | null>(null);
  const [logs, setLogs] = useState<InjectionLog[]>([]);
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const scheduleDebouncedInject = (vssPath: string, value: any, label: string, delayMs = 150) => {
    if (debounceTimers.current[vssPath]) {
      clearTimeout(debounceTimers.current[vssPath]);
    }
    debounceTimers.current[vssPath] = setTimeout(() => {
      delete debounceTimers.current[vssPath];
      handleInject(vssPath, value, label);
    }, delayMs);
  };

  const injectImmediate = (vssPath: string, value: any, label: string) => {
    if (debounceTimers.current[vssPath]) {
      clearTimeout(debounceTimers.current[vssPath]);
      delete debounceTimers.current[vssPath];
    }
    handleInject(vssPath, value, label);
  };

  const recordLog = (signal: string, value: any, latency_ms: number, propName: string) => {
    const newEntry: InjectionLog = {
      id: Math.random().toString(36).substring(7),
      time: new Date().toLocaleTimeString(),
      signal,
      value: String(value),
      latency_ms,
      propName,
    };
    setLogs((prev) => [newEntry, ...prev.slice(0, 14)]);
  };

  const handleInject = async (vssPath: string, value: any, label: string) => {
    if (!activeInst) return;
    try {
      setLoadingSignal(label);
      const res = await api.injectSignal(activeInst.instance_id, vssPath, value);
      recordLog(vssPath, res.injected_value ?? value, res.latency_ms ?? 0, res.vhal_property_name || 'VHAL');
    } catch (err: any) {
      alert(`Injection error: ${err.message}`);
    } finally {
      setLoadingSignal(null);
    }
  };

  const handleGearChange = (gear: 'PARK' | 'REVERSE' | 'NEUTRAL' | 'DRIVE') => {
    setCurrentGear(gear);
    handleInject('Vehicle.Powertrain.Transmission.SelectedGear', `GEAR_${gear}`, `GEAR_${gear}`);
  };

  const handleSpeedChange = (val: number, immediate = false) => {
    setSpeedKmh(val);
    if (immediate) {
      injectImmediate('Vehicle.Speed', val, `Speed ${val} km/h`);
    } else {
      scheduleDebouncedInject('Vehicle.Speed', val, `Speed ${val} km/h`, 150);
    }
  };

  const handleIgnitionChange = (state: 'OFF' | 'ACC' | 'ON' | 'START') => {
    setIgnition(state);
    handleInject('Vehicle.LowVoltageSystemState', state, `Ignition ${state}`);
  };

  const handleBatteryChange = (soc: number, immediate = false) => {
    setBatterySoc(soc);
    if (immediate) {
      injectImmediate('Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed', soc, `SoC ${soc}%`);
    } else {
      scheduleDebouncedInject('Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed', soc, `SoC ${soc}%`, 150);
    }
  };

  const handlePortToggle = () => {
    const next = !chargePortOpen;
    setChargePortOpen(next);
    handleInject('Vehicle.Powertrain.TractionBattery.Charging.ChargePortFlap', next, `Port ${next ? 'Open' : 'Closed'}`);
  };

  const handleCableToggle = () => {
    const next = !cableConnected;
    setCableConnected(next);
    handleInject('Vehicle.Powertrain.TractionBattery.Charging.IsChargingCableConnected', next, `Cable ${next ? 'Connected' : 'Disconnected'}`);
  };

  const handleBrakeToggle = () => {
    const next = !parkingBrakeOn;
    setParkingBrakeOn(next);
    handleInject('Vehicle.Chassis.ParkingBrake.IsEngaged', next, `Brake ${next ? 'On' : 'Off'}`);
  };

  const handleTempChange = (temp: number) => {
    setHvacTemp(temp);
    handleInject('Vehicle.Cabin.HVAC.Station.Row1.Driver.Temperature', temp, `HVAC ${temp}°C`);
  };

  if (onlineInstances.length === 0) {
    return (
      <div className="glass-panel p-10 text-center text-slate-400">
        <ShieldAlert className="w-8 h-8 text-amber-500 mx-auto mb-2" />
        <h3 className="text-sm font-bold text-white mb-1">No Active Online Cockpit</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          Signal injection requires a live AAOS instance. Go to the <strong>Virtual Fleet</strong> tab and boot an instance (VAR-A, VAR-B, or VAR-C) first.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Target Selector Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 glass-panel p-4">
        <div>
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            Interactive Vehicle HAL Signal Deck (Spec §6 & Appendix A)
          </h2>
          <p className="text-xs text-slate-400">
            Send atomic VSS signal events directly to the running AAOS cockpit via Android `car_service`.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-400 font-mono">Target Cockpit:</label>
          <select
            value={activeInst?.instance_id}
            onChange={(e) => setSelectedInstanceId(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-mono focus:border-blue-500 focus:outline-none"
          >
            {onlineInstances.map((inst) => (
              <option key={inst.instance_id} value={inst.instance_id}>
                {inst.variant_id} — {inst.vin_like} ({inst.adb_serial})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls Column 1 & 2 */}
        <div className="lg:col-span-2 space-y-5">
          {/* Powertrain & Transmission */}
          <div className="glass-panel p-5">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
              <Power className="w-4 h-4 text-blue-400" />
              Powertrain & Gear Selection (M2-FR1)
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              {/* Gear Buttons */}
              <div>
                <label className="text-xs text-slate-400 mb-2 block font-medium">Transmission Selector</label>
                <div className="grid grid-cols-4 gap-2">
                  {(['PARK', 'REVERSE', 'NEUTRAL', 'DRIVE'] as const).map((gear) => (
                    <button
                      key={gear}
                      onClick={() => handleGearChange(gear)}
                      disabled={loadingSignal !== null}
                      className={`py-3 rounded-xl text-center font-bold text-sm transition-all ${
                        currentGear === gear
                          ? gear === 'REVERSE'
                            ? 'bg-red-600 text-white shadow-lg shadow-red-600/40 ring-2 ring-red-400'
                            : 'bg-blue-600 text-white shadow-lg shadow-blue-600/40 ring-2 ring-blue-400'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {gear[0]}
                      <span className="block text-[10px] font-normal tracking-tight opacity-75">{gear}</span>
                    </button>
                  ))}
                </div>
                <div className="mt-2 text-[11px] text-slate-400 font-mono">
                  Current: <strong className="text-white">{currentGear}</strong> (VHAL: GEAR_SELECTION)
                </div>
              </div>

              {/* Ignition State */}
              <div>
                <label className="text-xs text-slate-400 mb-2 block font-medium">Ignition State (LowVoltageSystemState)</label>
                <div className="grid grid-cols-4 gap-2">
                  {(['OFF', 'ACC', 'ON', 'START'] as const).map((st) => (
                    <button
                      key={st}
                      onClick={() => handleIgnitionChange(st)}
                      disabled={loadingSignal !== null}
                      className={`py-2 rounded-lg text-xs font-semibold ${
                        ignition === st
                          ? 'bg-amber-600 text-white shadow-md shadow-amber-600/30'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <span className="text-xs text-slate-400">Parking Brake:</span>
                  <button
                    onClick={handleBrakeToggle}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold font-mono transition-all ${
                      parkingBrakeOn
                        ? 'bg-red-950/80 text-red-400 border border-red-800/80 shadow-sm shadow-red-900/40'
                        : 'bg-slate-800 text-slate-400 border border-slate-700'
                    }`}
                  >
                    {parkingBrakeOn ? 'ENGAGED (1)' : 'RELEASED (0)'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Speed & UX Restriction Interlock */}
          <div className="glass-panel p-5">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Gauge className="w-4 h-4 text-emerald-400" />
                Vehicle Speed (UX Restriction Trigger)
              </h3>
              <div className="text-right font-mono">
                <span className="text-xl font-bold text-emerald-400">{speedKmh}</span>
                <span className="text-xs text-slate-400 ml-1">km/h</span>
                <span className="text-xs text-slate-500 ml-2">
                  (~{Math.round(speedKmh / 1.60934)} MPH on screen)
                </span>
              </div>
            </div>

            <input
              type="range"
              min={0}
              max={120}
              step={5}
              value={speedKmh}
              onChange={(e) => handleSpeedChange(Number(e.target.value), false)}
              onMouseUp={(e) => handleSpeedChange(Number((e.target as HTMLInputElement).value), true)}
              onTouchEnd={(e) => handleSpeedChange(Number((e.target as HTMLInputElement).value), true)}
              className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500 my-4"
            />

            <div className="flex justify-between text-[11px] font-mono text-slate-400 mb-3">
              <button onClick={() => handleSpeedChange(0, true)} className="hover:text-white px-2 py-1 bg-slate-800/80 rounded">0 km/h (Parked)</button>
              <button onClick={() => handleSpeedChange(15, true)} className="hover:text-white px-2 py-1 bg-slate-800/80 rounded">15 km/h (UX Lock)</button>
              <button onClick={() => handleSpeedChange(50, true)} className="hover:text-white px-2 py-1 bg-slate-800/80 rounded">50 km/h (Urban)</button>
              <button onClick={() => handleSpeedChange(80, true)} className="hover:text-white px-2 py-1 bg-slate-800/80 rounded">80 km/h</button>
              <button onClick={() => handleSpeedChange(120, true)} className="hover:text-white px-2 py-1 bg-slate-800/80 rounded">120 km/h (Hwy)</button>
            </div>

            <div className="bg-slate-900/80 rounded-lg p-2.5 text-[11px] text-slate-400 border border-slate-800">
              💡 <strong>How to verify on emulator:</strong> In stock AOSP, speed triggers <code>CarUxRestrictions</code> (open Settings → tap Search; typing is blocked when speed &gt; 0). In <strong>Module 3</strong>, our custom OEM App (<code>APP-1</code>) renders the visual digital speedometer gauge directly on the centre console!
            </div>
          </div>

          {/* EV Traction Battery & Charging Station */}
          <div className="glass-panel p-5">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <BatteryCharging className="w-4 h-4 text-cyan-400" />
                EV Traction Battery & Charging (M2-FR1)
              </h3>
              <div className="text-right font-mono">
                <span className="text-lg font-bold text-cyan-400">{batterySoc}%</span>
                <span className="text-xs text-slate-500 ml-2">
                  ({Math.round((batterySoc / 100) * 75000)} Wh)
                </span>
              </div>
            </div>

            <input
              type="range"
              min={5}
              max={100}
              step={5}
              value={batterySoc}
              onChange={(e) => handleBatteryChange(Number(e.target.value), false)}
              onMouseUp={(e) => handleBatteryChange(Number((e.target as HTMLInputElement).value), true)}
              onTouchEnd={(e) => handleBatteryChange(Number((e.target as HTMLInputElement).value), true)}
              className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 my-3"
            />

            <div className="grid grid-cols-2 gap-3 mt-4">
              <button
                onClick={handlePortToggle}
                className={`p-2.5 rounded-lg text-xs font-mono font-semibold flex items-center justify-between border ${
                  chargePortOpen
                    ? 'bg-cyan-950/70 border-cyan-700 text-cyan-300'
                    : 'bg-slate-900 border-slate-800 text-slate-400'
                }`}
              >
                <span>Charge Port Flap:</span>
                <span>{chargePortOpen ? 'OPEN (1)' : 'CLOSED (0)'}</span>
              </button>

              <button
                onClick={handleCableToggle}
                className={`p-2.5 rounded-lg text-xs font-mono font-semibold flex items-center justify-between border ${
                  cableConnected
                    ? 'bg-emerald-950/70 border-emerald-700 text-emerald-300'
                    : 'bg-slate-900 border-slate-800 text-slate-400'
                }`}
              >
                <span>Charging Cable:</span>
                <span>{cableConnected ? 'PLUGGED (1)' : 'UNPLUGGED (0)'}</span>
              </button>
            </div>
          </div>

          {/* Cabin HVAC */}
          <div className="glass-panel p-5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <Thermometer className="w-5 h-5 text-amber-400" />
              <div>
                <h4 className="text-xs font-bold text-white">Driver Cabin Temperature</h4>
                <p className="text-[11px] text-slate-400 font-mono">HVAC_TEMPERATURE_SET (Row 1 Driver)</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="range"
                min={16.0}
                max={28.0}
                step={0.5}
                value={hvacTemp}
                onChange={(e) => handleTempChange(Number(e.target.value))}
                className="w-32 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-400"
              />
              <span className="text-sm font-bold font-mono text-amber-400 w-12 text-right">{hvacTemp.toFixed(1)}°C</span>
            </div>
          </div>
        </div>

        {/* Column 3: Live Injected Signals Feed & Latency */}
        <div className="space-y-4">
          <div className="glass-panel p-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
              <History className="w-3.5 h-3.5 text-blue-400" />
              Live Injection Feed (Telemetry)
            </h3>

            {logs.length === 0 ? (
              <div className="text-center py-10 text-xs text-slate-500 font-mono">
                Trigger any control to see live ADB injection timings...
              </div>
            ) : (
              <div className="space-y-2 max-h-[550px] overflow-y-auto pr-1">
                {logs.map((log) => (
                  <div key={log.id} className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg text-xs font-mono space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-blue-300 font-semibold truncate max-w-[150px]">{log.propName}</span>
                      <span className="text-[10px] text-slate-500">{log.time}</span>
                    </div>

                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-300 truncate max-w-[140px]">{log.signal.split('.').slice(-2).join('.')}</span>
                      <span className="text-amber-300 font-bold">{log.value}</span>
                    </div>

                    <div className="flex items-center justify-between text-[10px] pt-1 border-t border-slate-800/80">
                      <span className="text-slate-500">Latency:</span>
                      <span className={`font-semibold ${log.latency_ms < 500 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {log.latency_ms.toFixed(1)} ms {log.latency_ms < 500 && '✓'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
