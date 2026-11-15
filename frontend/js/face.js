// Face scanning in the browser. The live camera video NEVER leaves the phone/laptop:
// face-api turns it into 128 numbers (a "descriptor") and only those numbers are sent when joining a session.
// The ONLY picture ever sent is the one small cropped photo taken at the very first face setup (it becomes the profile picture).
const FaceScan = {
    loaded: false, stream: null, lastBox: null,

    async load() {
        if (this.loaded) return;
        await faceapi.tf.ready();
        await faceapi.nets.tinyFaceDetector.loadFromUri('/vendor/face');
        await faceapi.nets.faceLandmark68TinyNet.loadFromUri('/vendor/face');
        await faceapi.nets.faceRecognitionNet.loadFromUri('/vendor/face');
        this.loaded = true;
    },

    async startCamera(video) {
        this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
        video.srcObject = this.stream;
        await video.play();
    },

    stopCamera(video) {
        if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; }
        if (video) video.srcObject = null;
    },

    // A small square JPEG (256 px) of the face found by the last findFace() call: used once, as the profile picture.
    snapshotJpeg(video, size) {
        size = size || 256;
        const vw = video.videoWidth, vh = video.videoHeight, b = this.lastBox;
        let side = Math.min(vw, vh), sx = (vw - side) / 2, sy = (vh - side) / 2;               // fallback: centre square
        if (b) {                                                                                // crop around the face with some margin
            side = Math.min(Math.max(b.width, b.height) * 1.7, vw, vh);
            sx = Math.min(Math.max(b.x + b.width / 2 - side / 2, 0), vw - side);
            sy = Math.min(Math.max(b.y + b.height / 2 - side / 2, 0), vh - side);
        }
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = size;
        canvas.getContext('2d').drawImage(video, sx, sy, side, side, 0, 0, size, size);
        return new Promise((res, rej) => canvas.toBlob(b2 => b2 ? res(b2) : rej(new Error('Could not take the picture.')), 'image/jpeg', 0.85));
    },

    // Looks at the live video until exactly one face is found (or the time runs out). Returns 128 numbers, or null.
    async findFace(video, timeoutMs, shouldStop) {
        const opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
        const end = Date.now() + (timeoutMs || 10000);
        while (Date.now() < end) {
            if (shouldStop && shouldStop()) return null;
            const found = await faceapi.detectSingleFace(video, opts).withFaceLandmarks(true).withFaceDescriptor();
            if (found) { this.lastBox = found.detection.box; return Array.from(found.descriptor); }
            await new Promise(r => setTimeout(r, 200));
        }
        return null;
    },
};
