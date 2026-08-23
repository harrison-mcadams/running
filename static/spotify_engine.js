/**
 * Spotify Web API & Web Playback SDK Engine
 * Handles Spotify OAuth 2.0 Token, Track Metadata, BPM Analysis, and Player Controls
 */

class SpotifyEngine {
    constructor() {
        this.accessToken = localStorage.getItem('spotify_access_token') || null;
        this.player = null;
        this.deviceId = null;

        this.currentTrack = {
            id: 'demo-1',
            title: "Can't Hold Us",
            artist: "Macklemore & Ryan Lewis",
            bpm: 146.0,
            albumArt: "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300&q=80",
            isPlaying: false
        };

        // Preset High-Energy Workout Demo Catalog (Pre-analyzed Spotify Track BPMs)
        this.demoTracks = [
            {
                id: 'demo-1',
                title: "Can't Hold Us",
                artist: "Macklemore & Ryan Lewis",
                bpm: 146.0,
                albumArt: "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300&q=80"
            },
            {
                id: 'demo-2',
                title: "Blinding Lights",
                artist: "The Weeknd",
                bpm: 171.0,
                albumArt: "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=300&q=80"
            },
            {
                id: 'demo-3',
                title: "Titanium (ft. Sia)",
                artist: "David Guetta",
                bpm: 126.0,
                albumArt: "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=300&q=80"
            },
            {
                id: 'demo-4',
                title: "Eye of the Tiger",
                artist: "Survivor",
                bpm: 109.0,
                albumArt: "https://images.unsplash.com/photo-1498038432885-c6f3f1b912ee?w=300&q=80"
            }
        ];

        this.initSpotifySDK();
        this.updateHUD();
    }

    initSpotifySDK() {
        if (this.accessToken) {
            // Load official Spotify Web Playback SDK
            window.onSpotifyWebPlaybackSDKReady = () => {
                this.player = new Spotify.Player({
                    name: 'PedalSync Watch Player',
                    getOAuthToken: cb => { cb(this.accessToken); },
                    volume: 0.8
                });

                this.player.addListener('ready', ({ device_id }) => {
                    this.deviceId = device_id;
                    this.updateStatus('✅ Spotify Connected: PedalSync Player');
                });

                this.player.addListener('player_state_changed', state => {
                    if (!state) return;
                    const track = state.track_window.current_track;
                    if (track) {
                        this.currentTrack.title = track.name;
                        this.currentTrack.artist = track.artists.map(a => a.name).join(', ');
                        this.currentTrack.albumArt = track.album.images[0]?.url || this.currentTrack.albumArt;
                        this.currentTrack.isPlaying = !state.paused;

                        this.fetchTrackBpm(track.id);
                        this.updateHUD();
                    }
                });

                this.player.connect();
            };

            const script = document.createElement('script');
            script.src = 'https://sdk.scdn.co/spotify-player.js';
            document.head.appendChild(script);
        }
    }

    async fetchTrackBpm(trackId) {
        if (!this.accessToken || !trackId) return;

        try {
            const res = await fetch(`https://api.spotify.com/v1/audio-features/${trackId}`, {
                headers: { 'Authorization': `Bearer ${this.accessToken}` }
            });
            const data = await res.json();
            if (data && data.tempo) {
                this.currentTrack.bpm = Math.round(data.tempo * 10) / 10;
                
                // Update Adaptive Audio engine base BPM
                if (window.adaptiveAudio) {
                    window.adaptiveAudio.baseTrackBpm = this.currentTrack.bpm;
                }
                this.updateHUD();
            }
        } catch (e) {
            console.warn("Spotify audio features error:", e);
        }
    }

    selectDemoTrack(index) {
        if (index >= 0 && index < this.demoTracks.length) {
            const t = this.demoTracks[index];
            this.currentTrack.title = t.title;
            this.currentTrack.artist = t.artist;
            this.currentTrack.bpm = t.bpm;
            this.currentTrack.albumArt = t.albumArt;

            if (window.adaptiveAudio) {
                window.adaptiveAudio.baseTrackBpm = t.bpm;
            }
            this.updateHUD();
        }
    }

    togglePlay() {
        if (this.player && this.accessToken) {
            this.player.togglePlay();
        } else {
            // Demo mode toggle via Web Audio
            if (window.adaptiveAudio) {
                this.currentTrack.isPlaying = window.adaptiveAudio.togglePlay();
                this.updateHUD();
            }
        }
    }

    updateHUD() {
        const artEl = document.getElementById('spotify-album-art');
        const titleEl = document.getElementById('spotify-track-title');
        const artistEl = document.getElementById('spotify-track-artist');
        const bpmEl = document.getElementById('spotify-track-bpm');
        const btnPlay = document.getElementById('btn-spotify-play');

        if (artEl) artEl.src = this.currentTrack.albumArt;
        if (titleEl) titleEl.textContent = this.currentTrack.title;
        if (artistEl) artistEl.textContent = this.currentTrack.artist;
        if (bpmEl) bpmEl.textContent = `${this.currentTrack.bpm} BPM`;

        if (btnPlay) {
            btnPlay.textContent = this.currentTrack.isPlaying ? '⏸ Pause' : '▶ Play';
        }
    }

    updateStatus(msg) {
        const statusEl = document.getElementById('spotify-status');
        if (statusEl) statusEl.textContent = msg;
    }

    loginWithClientId(clientId) {
        if (!clientId) {
            alert("Please enter your Spotify Client ID");
            return;
        }
        window.location.href = `/spotify/login?client_id=${encodeURIComponent(clientId)}`;
    }
}

// Global Spotify Engine Instance
window.addEventListener('DOMContentLoaded', () => {
    window.spotifyEngine = new SpotifyEngine();

    const btnConnect = document.getElementById('btn-spotify-connect');
    const clientIdInput = document.getElementById('spotify-client-id');
    if (btnConnect) {
        btnConnect.addEventListener('click', () => {
            const clientId = clientIdInput ? clientIdInput.value.trim() : '';
            window.spotifyEngine.loginWithClientId(clientId);
        });
    }

    const btnPlay = document.getElementById('btn-spotify-play');
    if (btnPlay) {
        btnPlay.addEventListener('click', () => {
            window.spotifyEngine.togglePlay();
        });
    }

    // Demo Track Buttons
    const demoButtons = document.querySelectorAll('.spotify-demo-btn');
    demoButtons.forEach((btn, idx) => {
        btn.addEventListener('click', () => {
            demoButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.spotifyEngine.selectDemoTrack(idx);
        });
    });
});
