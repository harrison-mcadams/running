/**
 * Motion Cadence & Music Beat-Matching Real-time Engine
 * Features: 5-Point Centered Window Primary Peak Detector (Ignores noise, locks only on big cycling crests)
 */

class RhythmEngine {
    constructor() {
        this.sampleRate = 50; // Hz
        this.targetBpm = 140; // Music BPM
        this.motionCadenceRpm = 140; // Simulated or detected motion RPM
        
        // Input Mode: 'synthetic' | 'device' | 'network' | 'csv'
        this.inputMode = 'synthetic';
        
        // Motion Axis: 'vertical' (Earth-aligned Up/Down) | 'magnitude' | 'z' | 'y'
        this.motionAxis = 'vertical';

        // Stable Gravity Vector Memory
        this.gx = 0.0;
        this.gy = 0.0;
        this.gz = 9.81;

        // Web Audio Context
        this.audioCtx = null;
        this.isPlaying = false;
        this.nextBeatTime = 0;
        this.beatTimerId = null;

        // Zero-Lag DC Blocker Filter Memory
        this.prevRawX = 0;
        this.prevFiltY = 0;

        // Data Ring Buffers (Typed Arrays)
        this.bufferLength = 250; // 5 seconds at 50Hz
        this.rawSignal = new Float32Array(this.bufferLength);
        this.filteredSignal = new Float32Array(this.bufferLength);
        this.peakMarkers = new Uint8Array(this.bufferLength);
        this.bufferHead = 0; // Ring index
        
        // Network FIFO Queue
        this.networkQueue = [];

        // Peak Calibration Settings
        this.sensitivity = 0.5; // Multiplier k for adaptive threshold
        this.minPeakDistanceSec = 0.25; // Default lockout (min 250ms = up to 240 BPM)
        this.currentThreshold = 0.20;
        this.lastPeakAmp = 0.0;
        this.lastIntervalMs = 428; // default 140 RPM
        this.currentRpm = 140.0;
        this.totalStrokes = 0;

        // Detected Motion Peak Timestamps (relative seconds)
        this.motionPeakTimes = [];
        this.songBeatTimes = [];
        
        // Current Computed Metrics
        this.metrics = {
            cadenceRpm: 140.0,
            tempoScore: 0,
            phaseLockScore: 0,
            overallMatchScore: 0,
            offsetMs: 0,
            status: 'STANDBY'
        };

        // Voice Coach & Audio Feedback State (Disabled by default)
        this.voiceEnabled = false;
        this.chimesEnabled = false;
        this.lastVoiceTime = 0;
        this.lastStatus = '';

        // Simulation Parameters
        this.noiseLevel = 0.5;
        this.phaseShiftMs = 0;
        this.jitterMs = 15;

        // Device Motion Diagnostics
        this.deviceSampleCount = 0;
        this.deviceMotionBound = false;

        this.initCanvas();
        this.initNetworkPolling();
        this.startLoops();
    }

    // --- 1. Web Audio Engine & Metronome ---
    initAudio() {
        if (!this.audioCtx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            this.audioCtx = new AudioCtx();
        }
        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }
    }

    toggleAudio() {
        this.initAudio();
        this.isPlaying = !this.isPlaying;
        if (this.isPlaying) {
            this.nextBeatTime = this.audioCtx.currentTime + 0.05;
            this.scheduler();
        } else {
            if (this.beatTimerId) clearTimeout(this.beatTimerId);
        }
        return this.isPlaying;
    }

    scheduler() {
        while (this.nextBeatTime < this.audioCtx.currentTime + 0.1) {
            this.playBeatTick(this.nextBeatTime);
            const nowRelSec = performance.now() / 1000.0;
            this.songBeatTimes.push(nowRelSec);
            if (this.songBeatTimes.length > 30) this.songBeatTimes.shift();
            this.triggerBeatPulse();

            const beatInterval = 60.0 / this.targetBpm;
            this.nextBeatTime += beatInterval;
        }
        if (this.isPlaying) {
            this.beatTimerId = setTimeout(() => this.scheduler(), 25);
        }
    }

    playBeatTick(time) {
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, time);
        gain.gain.setValueAtTime(0.3, time);
        gain.gain.exponentialRampToValueAtTime(0.001, time + 0.05);

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);

        osc.start(time);
        osc.stop(time + 0.05);
    }

    playChime(type) {
        if (!this.chimesEnabled || !this.audioCtx) return;

        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        const now = this.audioCtx.currentTime;

        if (type === 'sync') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1046.5, now);
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        } else if (type === 'off') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(196.0, now);
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
        }

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.3);
    }

    speakVoiceFeedback(message) {
        if (!this.voiceEnabled || !('speechSynthesis' in window)) return;

        const now = performance.now();
        if (now - this.lastVoiceTime < 8000) return;
        this.lastVoiceTime = now;

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.rate = 1.1;
        utterance.pitch = 1.0;
        window.speechSynthesis.speak(utterance);
    }

    triggerBeatPulse() {
        const el = document.getElementById('pulse-beat');
        if (el) {
            el.classList.add('active-beat');
            setTimeout(() => el.classList.remove('active-beat'), 80);
        }
    }

    triggerMotionPulse() {
        const el = document.getElementById('pulse-motion');
        if (el) {
            el.classList.add('active-motion');
            setTimeout(() => el.classList.remove('active-motion'), 80);
        }

        const banner = document.getElementById('watch-beat-banner');
        const liveRpm = document.getElementById('watch-live-rpm');
        const liveInterval = document.getElementById('watch-live-interval');

        if (banner) {
            banner.classList.add('flash');
            setTimeout(() => banner.classList.remove('flash'), 120);
        }
        if (liveRpm) liveRpm.textContent = `${this.metrics.cadenceRpm}`;
        if (liveInterval) liveInterval.textContent = `${this.lastIntervalMs} ms`;
    }

    // --- 2. Clean Zero-Lag High-Pass Filter ---
    applyFilter(val) {
        const R = 0.92;
        const filtered = R * (this.prevFiltY + val - this.prevRawX);
        this.prevRawX = val;
        this.prevFiltY = filtered;
        return filtered;
    }

    // --- 3. Earth-Aligned Vertical Acceleration Processor ---
    process3DAccel(ax, ay, az) {
        let signalVal = 0.0;

        if (this.motionAxis === 'vertical') {
            // Stable gravity vector tracking
            this.gx = this.gx * 0.90 + ax * 0.10;
            this.gy = this.gy * 0.90 + ay * 0.10;
            this.gz = this.gz * 0.90 + az * 0.10;

            const gNorm = Math.sqrt(this.gx * this.gx + this.gy * this.gy + this.gz * this.gz) || 9.81;
            const vertAccel = ((ax * this.gx + ay * this.gy + az * this.gz) / gNorm) - 9.81;
            signalVal = vertAccel + 9.81;
        } else if (this.motionAxis === 'z') {
            signalVal = az + 9.81;
        } else if (this.motionAxis === 'y') {
            signalVal = ay + 9.81;
        } else {
            signalVal = Math.sqrt(ax * ax + ay * ay + az * az);
        }

        this.processSample(signalVal);
    }

    processSample(rawVal) {
        const nowRelSec = performance.now() / 1000.0;
        const filteredVal = this.applyFilter(rawVal);

        this.rawSignal[this.bufferHead] = rawVal;
        this.filteredSignal[this.bufferHead] = filteredVal;
        this.peakMarkers[this.bufferHead] = 0;

        // Dynamic adaptive threshold from rolling std dev
        let sum = 0;
        let sumSq = 0;
        const n = 35;
        for (let i = 0; i < n; i++) {
            const idx = (this.bufferHead - i + this.bufferLength) % this.bufferLength;
            const v = this.filteredSignal[idx];
            sum += v;
            sumSq += v * v;
        }
        const mean = sum / n;
        const variance = Math.max(0, (sumSq / n) - (mean * mean));
        const stdDev = Math.sqrt(variance);

        // Adaptive threshold cutoff
        this.currentThreshold = Math.max(0.12, Math.abs(mean) + (this.sensitivity * stdDev * 1.2));

        // 5-Point Centered Window Primary Peak Detector (Ignores noise, locks only on big primary crest)
        const p2Idx = (this.bufferHead - 4 + this.bufferLength) % this.bufferLength;
        const p1Idx = (this.bufferHead - 3 + this.bufferLength) % this.bufferLength;
        const currIdx = (this.bufferHead - 2 + this.bufferLength) % this.bufferLength;
        const n1Idx = (this.bufferHead - 1 + this.bufferLength) % this.bufferLength;
        const n2Idx = (this.bufferHead + this.bufferLength) % this.bufferLength;

        const p = this.filteredSignal[currIdx];
        const p2 = this.filteredSignal[p2Idx];
        const p1 = this.filteredSignal[p1Idx];
        const n1 = this.filteredSignal[n1Idx];
        const n2 = this.filteredSignal[n2Idx];

        // Adaptive Refractory Lockout
        const adaptiveLockout = Math.min(this.minPeakDistanceSec, Math.max(0.18, (this.lastIntervalMs / 1000.0) * 0.45));

        // Strictly require 5-point local max AND threshold clearance
        const isTruePrimaryPeak = (p > p2 && p > p1 && p > n1 && p >= n2) && (p > this.currentThreshold);

        if (isTruePrimaryPeak) {
            const lastPeak = this.motionPeakTimes[this.motionPeakTimes.length - 1] || 0;
            const intervalSec = nowRelSec - lastPeak;

            if (intervalSec > adaptiveLockout) {
                this.motionPeakTimes.push(nowRelSec);
                if (this.motionPeakTimes.length > 20) this.motionPeakTimes.shift();

                this.peakMarkers[currIdx] = 1; // Mark primary peak for visual pink dot
                this.lastPeakAmp = p;
                
                if (lastPeak > 0 && intervalSec > 0.15 && intervalSec < 1.5) {
                    this.lastIntervalMs = Math.round(intervalSec * 1000.0);
                    
                    const instantRpm = (1.0 / intervalSec) * 60.0;
                    if (instantRpm >= 40 && instantRpm <= 250) {
                        this.currentRpm = this.currentRpm * 0.60 + instantRpm * 0.40;
                        this.metrics.cadenceRpm = this.currentRpm.toFixed(1);
                    }
                }
                this.totalStrokes++;

                this.triggerMotionPulse();
            }
        }

        this.bufferHead = (this.bufferHead + 1) % this.bufferLength;

        // Evaluate overall sync metrics
        this.evaluateMetrics();
    }

    // --- 4. Device Motion API Handling ---
    async activateDeviceMotion() {
        const statusEl = document.getElementById('device-sensor-status');

        if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
            try {
                const permission = await DeviceMotionEvent.requestPermission();
                if (permission !== 'granted') {
                    if (statusEl) statusEl.textContent = '❌ Sensor permission denied by user.';
                    return false;
                }
            } catch (err) {
                console.warn(err);
            }
        }

        if (!this.deviceMotionBound) {
            window.addEventListener('devicemotion', (event) => {
                if (this.inputMode !== 'device') return;

                const acc = event.accelerationIncludingGravity || event.acceleration;
                if (acc && (acc.x !== null || acc.y !== null)) {
                    this.deviceSampleCount++;
                    const ax = acc.x || 0;
                    const ay = acc.y || 0;
                    const az = acc.z || 0;
                    
                    this.process3DAccel(ax, ay, az);

                    if (statusEl && this.deviceSampleCount % 10 === 0) {
                        statusEl.textContent = `⚡ Active: ${this.deviceSampleCount} samples`;
                    }
                }
            });
            this.deviceMotionBound = true;
        }

        if (statusEl) statusEl.textContent = '✅ Sensor listener active! Move/shake device...';
        return true;
    }

    initNetworkPolling() {
        setInterval(async () => {
            if (this.inputMode !== 'network') return;

            try {
                const res = await fetch('/api/imu_stream/latest');
                const samples = await res.json();

                if (samples && samples.length > 0) {
                    samples.forEach(s => {
                        this.networkQueue.push(s);
                    });
                    if (this.networkQueue.length > 20) {
                        this.networkQueue = this.networkQueue.slice(-20);
                    }
                }
            } catch (err) {
                console.warn('Network IMU fetch error:', err);
            }
        }, 30);
    }

    // --- 5. CSV File Log Reader ---
    loadCsvData(csvText) {
        const lines = csvText.split('\n').map(l => l.trim()).filter(l => l);
        if (lines.length < 2) return;

        const header = lines[0].toLowerCase().split(',');
        const axIdx = header.findIndex(h => h.includes('ax') || h.includes('accel_x') || h.includes('x'));
        const ayIdx = header.findIndex(h => h.includes('ay') || h.includes('accel_y') || h.includes('y'));
        const azIdx = header.findIndex(h => h.includes('az') || h.includes('accel_z') || h.includes('z'));

        let samples = [];
        for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(',').map(c => parseFloat(c.trim()));
            if (cols.length > Math.max(axIdx, ayIdx, azIdx)) {
                const ax = cols[axIdx] || 0;
                const ay = cols[ayIdx] || 0;
                const az = cols[azIdx] || 0;
                samples.push({ ax, ay, az });
            }
        }

        if (samples.length === 0) return;

        this.inputMode = 'csv';
        let idx = 0;
        const csvInterval = setInterval(() => {
            if (idx >= samples.length || this.inputMode !== 'csv') {
                clearInterval(csvInterval);
                return;
            }
            const s = samples[idx];
            this.process3DAccel(s.ax, s.ay, s.az);
            idx++;
        }, 1000 / this.sampleRate);
    }

    // --- 6. Metrics Computation ---
    evaluateMetrics() {
        if (this.motionPeakTimes.length < 2) return;

        const recentPeaks = this.motionPeakTimes.slice(-3);
        const cadenceRpm = parseFloat(this.metrics.cadenceRpm);

        const targets = [this.targetBpm, this.targetBpm / 2.0, this.targetBpm * 2.0];
        const bestTarget = targets.reduce((prev, curr) => 
            Math.abs(curr - cadenceRpm) < Math.abs(prev - cadenceRpm) ? curr : prev
        );
        const tempoError = Math.abs(cadenceRpm - bestTarget) / bestTarget;
        const tempoScore = Math.max(0, 100 * (1 - tempoError * 2.5));
        this.metrics.tempoScore = tempoScore.toFixed(1);

        const beatPeriod = 60.0 / bestTarget;
        let sumCos = 0;
        let sumSin = 0;
        let offsetsMs = [];

        recentPeaks.forEach(t => {
            const remainder = t % beatPeriod;
            const offset = remainder <= beatPeriod / 2 ? remainder : remainder - beatPeriod;
            offsetsMs.push(offset * 1000.0);

            const angle = (offset / beatPeriod) * 2 * Math.PI;
            sumCos += Math.cos(angle);
            sumSin += Math.sin(angle);
        });

        const N = recentPeaks.length;
        const R = Math.sqrt((sumCos / N) ** 2 + (sumSin / N) ** 2);
        const phaseLockScore = R * 100.0;
        this.metrics.phaseLockScore = phaseLockScore.toFixed(1);

        const avgOffset = offsetsMs.reduce((a, b) => a + b, 0) / offsetsMs.length;
        this.metrics.offsetMs = avgOffset.toFixed(1);

        const overall = (tempoScore * 0.4) + (phaseLockScore * 0.6);
        this.metrics.overallMatchScore = overall.toFixed(1);

        let newStatus = '';
        let voiceMsg = '';

        if (overall >= 82) {
            newStatus = 'IN SYNC! 🎯';
            voiceMsg = 'Perfect rhythm! You are in time with the music.';
            if (this.lastStatus !== 'sync') this.playChime('sync');
            this.lastStatus = 'sync';
        } else if (avgOffset > 25) {
            newStatus = `RUSHING (+${Math.round(avgOffset)}ms) ⚡`;
            voiceMsg = `You are rushing ${Math.abs(Math.round(avgOffset))} milliseconds ahead of the beat.`;
            if (this.lastStatus !== 'rushing') this.playChime('off');
            this.lastStatus = 'rushing';
        } else if (avgOffset < -25) {
            newStatus = `DRAGGING (${Math.round(avgOffset)}ms) 🐢`;
            voiceMsg = `Pick up your cadence, you are dragging ${Math.abs(Math.round(avgOffset))} milliseconds behind the beat.`;
            if (this.lastStatus !== 'dragging') this.playChime('off');
            this.lastStatus = 'dragging';
        } else {
            newStatus = 'OFF BEAT ⚠️';
            voiceMsg = 'Off beat. Reset your cadence to match the music.';
            if (this.lastStatus !== 'off') this.playChime('off');
            this.lastStatus = 'off';
        }

        this.metrics.status = newStatus;
        this.speakVoiceFeedback(voiceMsg);

        if (window.adaptiveAudio) {
            window.adaptiveAudio.updateCadence(parseFloat(this.metrics.cadenceRpm), this.targetBpm);
        }

        this.updateHUD();
    }

    updateHUD() {
        document.getElementById('metric-match').textContent = `${this.metrics.overallMatchScore}%`;
        document.getElementById('metric-cadence').textContent = `${this.metrics.cadenceRpm} RPM`;
        document.getElementById('metric-phaselock').textContent = `${this.metrics.phaseLockScore}%`;
        document.getElementById('metric-offset').textContent = `${this.metrics.offsetMs > 0 ? '+' : ''}${this.metrics.offsetMs} ms`;
        
        const cSync = document.getElementById('cockpit-sync-num');
        const cCadence = document.getElementById('cockpit-cadence-num');
        const cBpm = document.getElementById('cockpit-bpm-num');
        const cOffset = document.getElementById('cockpit-offset-num');
        const cPhase = document.getElementById('cockpit-phase-num');

        if (cSync) cSync.textContent = `${this.metrics.overallMatchScore}%`;
        if (cCadence) cCadence.textContent = `${Math.round(this.metrics.cadenceRpm)}`;
        if (cBpm) cBpm.textContent = `${Math.round(this.targetBpm)}`;
        if (cOffset) cOffset.textContent = `${this.metrics.offsetMs > 0 ? '+' : ''}${Math.round(this.metrics.offsetMs)}ms`;
        if (cPhase) cPhase.textContent = `${Math.round(this.metrics.phaseLockScore)}%`;

        const diagStrokes = document.getElementById('diag-strokes');
        const diagAmp = document.getElementById('diag-amp');
        const diagThresh = document.getElementById('diag-thresh');
        const diagInterval = document.getElementById('diag-interval');

        if (diagStrokes) diagStrokes.textContent = `${this.totalStrokes}`;
        if (diagAmp) diagAmp.textContent = `${this.lastPeakAmp.toFixed(2)} m/s²`;
        if (diagThresh) diagThresh.textContent = `${this.currentThreshold.toFixed(2)} m/s²`;
        if (diagInterval) diagInterval.textContent = `${this.lastIntervalMs} ms`;

        const statusEl = document.getElementById('status-tag');
        if (statusEl) {
            statusEl.textContent = this.metrics.status;
            statusEl.className = 'status-tag ' + (
                this.metrics.overallMatchScore >= 82 ? 'status-sync' :
                this.metrics.offsetMs > 25 ? 'status-rushing' : 'status-dragging'
            );
        }

        const coachText = document.getElementById('coach-text');
        const coachCard = document.getElementById('coach-card');
        if (coachText) {
            if (this.metrics.overallMatchScore >= 82) {
                coachText.textContent = "🎯 YOU ARE IN TIME WITH THE MUSIC!";
                if (coachCard) coachCard.style.borderColor = "#00ff88";
            } else if (this.metrics.offsetMs > 25) {
                coachText.textContent = `⚡ SLOW DOWN SLIGHTLY: Rushing by +${Math.round(this.metrics.offsetMs)}ms`;
                if (coachCard) coachCard.style.borderColor = "#ffb700";
            } else if (this.metrics.offsetMs < -25) {
                coachText.textContent = `🐢 PICK UP THE PACING: Dragging by ${Math.round(this.metrics.offsetMs)}ms`;
                if (coachCard) coachCard.style.borderColor = "#4facfe";
            } else {
                coachText.textContent = "⚠️ DRIFTING OFF BEAT — Lock back onto the music rhythm!";
                if (coachCard) coachCard.style.borderColor = "#ff007f";
            }
        }
    }

    // --- 7. Hardware-Accelerated 60 FPS Canvas Oscilloscope with Dynamic Threshold Line ---
    initCanvas() {
        this.canvas = document.getElementById('oscilloscope');
        if (this.canvas) {
            this.ctx = this.canvas.getContext('2d', { alpha: false });
            this.resizeCanvas();
            window.addEventListener('resize', () => this.resizeCanvas());
        }
    }

    resizeCanvas() {
        if (this.canvas) {
            this.canvas.width = this.canvas.parentElement.clientWidth;
            this.canvas.height = this.canvas.parentElement.clientHeight;
        }
    }

    drawOscilloscope() {
        if (!this.ctx) return;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const centerY = h / 2;

        this.ctx.fillStyle = '#05080f';
        this.ctx.fillRect(0, 0, w, h);

        // Center zero line
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(0, centerY);
        this.ctx.lineTo(w, centerY);
        this.ctx.stroke();

        // Dynamic Yellow Threshold Line
        const threshY = centerY - (this.currentThreshold * 35);
        this.ctx.strokeStyle = 'rgba(255, 183, 0, 0.4)';
        this.ctx.setLineDash([4, 4]);
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(0, threshY);
        this.ctx.lineTo(w, threshY);
        this.ctx.stroke();
        this.ctx.setLineDash([]); // Reset dash

        // 1. Draw Raw Motion Waveform (Dim Blue)
        this.ctx.strokeStyle = 'rgba(79, 172, 254, 0.35)';
        this.ctx.lineWidth = 1.5;
        this.ctx.beginPath();
        for (let i = 0; i < this.bufferLength; i++) {
            const ringIdx = (this.bufferHead + i) % this.bufferLength;
            const x = (i / this.bufferLength) * w;
            const y = centerY - ((this.rawSignal[ringIdx] - 9.81) * 8);
            if (i === 0) this.ctx.moveTo(x, y);
            else this.ctx.lineTo(x, y);
        }
        this.ctx.stroke();

        // 2. Draw Zero-Lag Filtered Motion Waveform (Neon Cyan)
        this.ctx.strokeStyle = '#00f2fe';
        this.ctx.lineWidth = 2.5;
        this.ctx.beginPath();
        for (let i = 0; i < this.bufferLength; i++) {
            const ringIdx = (this.bufferHead + i) % this.bufferLength;
            const x = (i / this.bufferLength) * w;
            const y = centerY - (this.filteredSignal[ringIdx] * 35);
            if (i === 0) this.ctx.moveTo(x, y);
            else this.ctx.lineTo(x, y);
        }
        this.ctx.stroke();

        // 3. Draw Visual Detected Motion Peak Markers (Neon Pink Dots)
        for (let i = 0; i < this.bufferLength; i++) {
            const ringIdx = (this.bufferHead + i) % this.bufferLength;
            if (this.peakMarkers[ringIdx] === 1) {
                const x = (i / this.bufferLength) * w;
                const y = centerY - (this.filteredSignal[ringIdx] * 35);

                this.ctx.fillStyle = '#ff007f';
                this.ctx.shadowColor = '#ff007f';
                this.ctx.shadowBlur = 12;
                this.ctx.beginPath();
                this.ctx.arc(x, y, 6, 0, 2 * Math.PI);
                this.ctx.fill();
                this.ctx.shadowBlur = 0;
            }
        }
    }

    startLoops() {
        let simTime = 0;
        const dt = 1.0 / this.sampleRate;

        // 1. Fixed 50Hz Data Processing Loop
        setInterval(() => {
            simTime += dt;

            if (this.inputMode === 'synthetic') {
                const motionFreq = this.motionCadenceRpm / 60.0;
                const phaseOffsetRad = (this.phaseShiftMs / 1000.0) * motionFreq * 2 * Math.PI;
                const jitterRad = (Math.random() - 0.5) * (this.jitterMs / 1000.0) * motionFreq * 2 * Math.PI;

                const baseSine = Math.sin(2 * Math.PI * motionFreq * simTime + phaseOffsetRad + jitterRad);
                const noise = (Math.random() - 0.5) * this.noiseLevel;
                
                const ay = 2.5 * baseSine + noise;
                const az = 9.81 + 0.5 * noise;
                this.process3DAccel(0, ay, az);
            } else if (this.inputMode === 'network') {
                if (this.networkQueue.length > 0) {
                    const sample = this.networkQueue.shift();
                    this.process3DAccel(sample.ax || 0, sample.ay || 0, sample.az || 0);
                }
            }
        }, 1000 / this.sampleRate);

        // 2. 60 FPS requestAnimationFrame Rendering Loop
        const render = () => {
            this.drawOscilloscope();
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    }
}

window.addEventListener('DOMContentLoaded', () => {
    window.rhythmEngine = new RhythmEngine();

    // Motion Axis Selector
    const axisSelector = document.getElementById('axis-selector');
    if (axisSelector) {
        axisSelector.addEventListener('change', (e) => {
            window.rhythmEngine.motionAxis = e.target.value;
        });
    }

    // Sensitivity Slider
    const sensitivitySlider = document.getElementById('sensitivity-slider');
    const sensitivityVal = document.getElementById('sensitivity-val');
    if (sensitivitySlider) {
        sensitivitySlider.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            sensitivityVal.textContent = val.toFixed(1);
            window.rhythmEngine.sensitivity = val;
        });
    }

    // Refractory Lockout Slider
    const lockoutSlider = document.getElementById('lockout-slider');
    const lockoutVal = document.getElementById('lockout-val');
    if (lockoutSlider) {
        lockoutSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            lockoutVal.textContent = `${val} ms`;
            window.rhythmEngine.minPeakDistanceSec = val / 1000.0;
        });
    }

    // Sliders
    const bpmSlider = document.getElementById('bpm-slider');
    const bpmVal = document.getElementById('bpm-val');
    if (bpmSlider) {
        bpmSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            bpmVal.textContent = val;
            window.rhythmEngine.targetBpm = val;
        });
    }

    const cadenceSlider = document.getElementById('cadence-slider');
    const cadenceVal = document.getElementById('cadence-val');
    if (cadenceSlider) {
        cadenceSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            cadenceVal.textContent = val;
            window.rhythmEngine.motionCadenceRpm = val;
        });
    }

    const phaseSlider = document.getElementById('phase-slider');
    const phaseVal = document.getElementById('phase-val');
    if (phaseSlider) {
        phaseSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            phaseVal.textContent = `${val > 0 ? '+' : ''}${val} ms`;
            window.rhythmEngine.phaseShiftMs = val;
        });
    }

    // Input Mode Tabs
    const tabs = document.querySelectorAll('.mode-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const mode = tab.getAttribute('data-mode');
            window.rhythmEngine.inputMode = mode;

            document.getElementById('sec-synthetic').style.display = mode === 'synthetic' ? 'block' : 'none';
            document.getElementById('sec-device').style.display = mode === 'device' ? 'block' : 'none';
            document.getElementById('sec-network').style.display = mode === 'network' ? 'block' : 'none';
            document.getElementById('sec-csv').style.display = mode === 'csv' ? 'block' : 'none';
        });
    });

    // Sensor Grant Button
    const btnGrant = document.getElementById('btn-grant-sensors');
    if (btnGrant) {
        btnGrant.addEventListener('click', () => {
            window.rhythmEngine.activateDeviceMotion();
        });
    }
});
