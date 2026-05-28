class AudioCapture {
    constructor(prospectId, onStatus, onEvent) {
        this.prospectId = prospectId;
        this.onStatus = onStatus || (() => {});
        this.onEvent = onEvent || (() => {});
        this.mediaRecorder = null;
        this.ws = null;
        this.stream = null;
        this.isRecording = false;
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 16000
            });

            const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            this.ws = new WebSocket(`${wsProto}//${window.location.host}/ws/audio/${this.prospectId}`);

            this.ws.onopen = () => {
                this.onStatus('connected');
                this.mediaRecorder.start(500);
                this.isRecording = true;
                this.onStatus('recording');
            };

            this.ws.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    this.onEvent(payload);
                } catch (e) {
                    this.onEvent({ type: 'raw', text: event.data });
                }
            };

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(e.data);
                }
            };

            this.ws.onclose = () => {
                this.onStatus('disconnected');
            };

            this.ws.onerror = () => {
                this.onStatus('error');
            };

        } catch (err) {
            console.error('🚫 Accès micro refusé:', err);
            this.onStatus('mic_error');
        }
    }

    stop() {
        this.isRecording = false;

        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.onstop = () => {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.close();
                }
            };
            this.mediaRecorder.stop();
        } else if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.close();
        }

        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
        }

        this.onStatus('stopped');
    }
}

window.AudioCapture = AudioCapture;
