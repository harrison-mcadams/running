/**
 * Adaptive Music Engine & Dynamic Tempo Synchronizer
 * Uses Web Audio API playbackRate modulation for Cadence Following & Entrainment
 */

class AdaptiveAudioEngine {
    constructor() {
        this.audioCtx = null;
        this.sourceNode = null;
        this.gainNode = null;
        this.audioBuffer = null;

        this.isPlaying = false;
        this.baseTrackBpm = 140.0; // Default beat loop tempo
        this.targetCadenceRpm = 140.0;
        
        // Mode: 'metronome' | 'follow' | 'entrain'
        this.mode = 'follow';

        // Playback Rate Controller Parameters
        this.currentRate = 1.0;
        this.targetRate = 1.0;
        this.minRate = 0.85; // Max 15% slow down
        this.maxRate = 1.15; // Max 15% speed up
        this.smoothingAlpha = 0.08; // EMA smoothing factor for audio stability

        this.initLoop();
    }

    initContext() {
        if (!this.audioCtx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            this.audioCtx = new AudioCtx();
            this.gainNode = this.audioCtx.createGain();
            this.gainNode.gain.value = 0.8;
            this.gainNode.connect(this.audioCtx.destination);
            
            // Generate procedural beat loop if no custom file loaded
            this.generateProceduralBeatBuffer();
        }
        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }
    }

    /**
     * Synthesizes a high-energy 4-bar cyber-drum & bass loop at 140 BPM procedurally
     */
    generateProceduralBeatBuffer() {
        if (!this.audioCtx) return;

        const duration = (60.0 / this.baseTrackBpm) * 8; // 8 beats = 2 bars
        const sampleRate = this.audioCtx.sampleRate;
        const totalSamples = Math.floor(duration * sampleRate);
        const buffer = this.audioCtx.createBuffer(2, totalSamples, sampleRate);
        
        const left = buffer.getChannelData(0);
        const right = buffer.getChannelData(1);

        const beatSec = 60.0 / this.baseTrackBpm;
        const subBeatSec = beatSec / 4; // 16th note interval

        for (let i = 0; i < totalSamples; i++) {
            const t = i / sampleRate;
            let sample = 0;

            // 1. Kick Drum on Beats 1, 3, 5, 7
            for (let b = 0; b < 8; b += 2) {
                const kickTime = b * beatSec;
                if (t >= kickTime && t < kickTime + 0.15) {
                    const dt = t - kickTime;
                    const freq = 120 * Math.exp(-dt * 30);
                    sample += 0.8 * Math.sin(2 * Math.PI * freq * dt) * Math.exp(-dt * 15);
                }
            }

            // 2. Snare Drum on Beats 2, 4, 6, 8
            for (let b = 1; b < 8; b += 2) {
                const snareTime = b * beatSec;
                if (t >= snareTime && t < snareTime + 0.18) {
                    const dt = t - snareTime;
                    const noise = (Math.random() - 0.5) * Math.exp(-dt * 20);
                    const tone = 0.4 * Math.sin(2 * Math.PI * 220 * dt) * Math.exp(-dt * 25);
                    sample += (noise * 0.7 + tone * 0.3);
                }
            }

            // 3. Hi-Hat on 8th notes
            const hihatStep = Math.floor(t / (beatSec / 2));
            const hihatTime = hihatStep * (beatSec / 2);
            if (t >= hihatTime && t < hihatTime + 0.05) {
                const dt = t - hihatTime;
                sample += 0.25 * (Math.random() - 0.5) * Math.exp(-dt * 50);
            }

            // 4. Driving Bass Synth Accent
            const bassNote = Math.sin(2 * Math.PI * 110 * t + Math.sin(t * 12));
            sample += 0.15 * bassNote * Math.sin(t * Math.PI * 4);

            left[i] = Math.max(-1, Math.min(1, sample));
            right[i] = left[i];
        }

        this.audioBuffer = buffer;
    }

    loadCustomAudioFile(file) {
        this.initContext();
        const reader = new FileReader();
        reader.onload = (e) => {
            const arrayBuffer = e.target.result;
            this.audioCtx.decodeAudioData(arrayBuffer, (decodedBuffer) => {
                this.audioBuffer = decodedBuffer;
                if (this.isPlaying) {
                    this.stop();
                    this.play();
                }
                const trackNameEl = document.getElementById('track-name');
                if (trackNameEl) trackNameEl.textContent = `🎵 Loaded: ${file.name}`;
            });
        };
        reader.readAsArrayBuffer(file);
    }

    togglePlay() {
        this.initContext();
        if (this.isPlaying) {
            this.stop();
        } else {
            this.play();
        }
        return this.isPlaying;
    }

    play() {
        if (!this.audioCtx || !this.audioBuffer) return;

        this.sourceNode = this.audioCtx.createBufferSource();
        this.sourceNode.buffer = this.audioBuffer;
        this.sourceNode.loop = true;
        this.sourceNode.playbackRate.value = this.currentRate;
        this.sourceNode.connect(this.gainNode);
        this.sourceNode.start(0);

        this.isPlaying = true;
    }

    stop() {
        if (this.sourceNode) {
            try {
                this.sourceNode.stop();
                this.sourceNode.disconnect();
            } catch (e) {}
            this.sourceNode = null;
        }
        this.isPlaying = false;
    }

    /**
     * Updates Adaptive Playback Speed based on live watch cadence
     */
    updateCadence(measuredRpm, targetRpm) {
        this.targetCadenceRpm = targetRpm;

        if (measuredRpm <= 0) return;

        if (this.mode === 'follow') {
            // 1. Follow Mode: Match song tempo directly to rider cadence
            this.targetRate = measuredRpm / this.baseTrackBpm;
        } else if (this.mode === 'entrain') {
            // 2. Entrainment Mode: Nudge tempo to pull rider into target cadence zone
            const deltaRpm = measuredRpm - targetRpm;
            
            if (deltaRpm < -2) {
                // Rider is pedalling SLOWER than target -> Speed up music slightly (+3% to +10%) to pull legs faster
                const pullFactor = Math.min(0.12, Math.abs(deltaRpm) * 0.008);
                this.targetRate = 1.0 + pullFactor;
            } else if (deltaRpm > 2) {
                // Rider is pedalling FASTER than target -> Slow down music slightly to ease cadence back to target
                const easeFactor = Math.min(0.12, deltaRpm * 0.008);
                this.targetRate = 1.0 - easeFactor;
            } else {
                // Perfectly in target zone (±2 RPM) -> 1.0x Rate
                this.targetRate = 1.0;
            }
        } else {
            // Static Metronome mode
            this.targetRate = 1.0;
        }

        // Clamp rate bounds [0.85x, 1.15x]
        this.targetRate = Math.max(this.minRate, Math.min(this.maxRate, this.targetRate));
    }

    /**
     * Smooth audio playbackRate update loop
     */
    initLoop() {
        setInterval(() => {
            // Exponential moving average for seamless pitch transitions
            this.currentRate += (this.targetRate - this.currentRate) * this.smoothingAlpha;

            if (this.sourceNode && this.audioCtx) {
                this.sourceNode.playbackRate.setValueAtTime(this.currentRate, this.audioCtx.currentTime);
            }

            this.updateUI();
        }, 50);
    }

    updateUI() {
        const rateEl = document.getElementById('metric-audio-rate');
        const bpmEl = document.getElementById('metric-audio-bpm');
        const percentEl = document.getElementById('metric-audio-percent');

        if (rateEl) rateEl.textContent = `${this.currentRate.toFixed(2)}x`;
        
        const effectiveBpm = (this.baseTrackBpm * this.currentRate).toFixed(1);
        if (bpmEl) bpmEl.textContent = `${effectiveBpm} BPM`;

        const percentDelta = ((this.currentRate - 1.0) * 100.0).toFixed(1);
        if (percentEl) {
            percentEl.textContent = `${percentDelta > 0 ? '+' : ''}${percentDelta}%`;
            percentEl.className = 'status-tag ' + (
                Math.abs(percentDelta) < 1.0 ? 'status-sync' :
                percentDelta > 0 ? 'status-rushing' : 'status-dragging'
            );
        }
    }
}

// Instantiate Global Adaptive Audio Engine
window.addEventListener('DOMContentLoaded', () => {
    window.adaptiveAudio = new AdaptiveAudioEngine();

    // Custom Audio File Selector
    const fileInput = document.getElementById('audio-file-input');
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                window.adaptiveAudio.loadCustomAudioFile(file);
            }
        });
    }

    // Audio Mode Selector
    const modeTabs = document.querySelectorAll('.audio-mode-tab');
    modeTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            modeTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const mode = tab.getAttribute('data-audio-mode');
            window.adaptiveAudio.mode = mode;

            const modeDesc = document.getElementById('audio-mode-desc');
            if (modeDesc) {
                modeDesc.textContent = mode === 'follow' ? 
                    '⚡ Cadence Follower: Music speeds up / slows down to match your pedalling 1:1.' :
                    mode === 'entrain' ?
                    '🎯 Target Entrainment: Music tempo nudges faster/slower to pull your legs into optimal target cadence.' :
                    '⏱ Static Tempo Metronome';
            }
        });
    });

    const playBtn = document.getElementById('btn-adaptive-play');
    if (playBtn) {
        playBtn.addEventListener('click', () => {
            const playing = window.adaptiveAudio.togglePlay();
            playBtn.textContent = playing ? '⏸ Pause Adaptive Music' : '▶ Play Adaptive Music';
            playBtn.className = playing ? 'btn btn-secondary' : 'btn';
        });
    }
});
