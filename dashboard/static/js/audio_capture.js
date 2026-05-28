class AudioCapture {
    constructor(prospectId, onStatus) {
        this.prospectId = prospectId;
        this.onStatus = onStatus || (() => {});
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

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0 && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(e.data);
                }
            };

            // Bug 2 fix : onclose ne rappelle plus stop()
            this.ws.onclose = () => { this.onStatus('disconnected'); };
            this.ws.onerror = () => { this.onStatus('error'); };

        } catch (err) {
            console.error('🚫 Accès micro refusé:', err);
            this.onStatus('mic_error');
        }
    }

    stop() {
        this.isRecording = false;
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            // Bug 2 fix : on ferme le WS APRÈS que le recorder a envoyé le dernier chunk
            this.mediaRecorder.onstop = () => {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.close();
            };
            this.mediaRecorder.stop();
        }
        if (this.stream) this.stream.getTracks().forEach(t => t.stop());
        this.onStatus('stopped');
    }
}

window.AudioCapture = AudioCapture;
