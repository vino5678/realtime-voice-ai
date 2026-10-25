export function CallSection() {
  return (
    <section className="panel call-panel" aria-labelledby="call-h">
      <div className="call-heading">
        <span className="call-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M8.5 4.75h-2A2.75 2.75 0 0 0 3.75 7.5v9A2.75 2.75 0 0 0 6.5 19.25h11a2.75 2.75 0 0 0 2.75-2.75v-9a2.75 2.75 0 0 0-2.75-2.75h-2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            <path d="M9 9.25a3 3 0 0 1 6 0v5.5a3 3 0 0 1-6 0v-5.5ZM12 20v-2.25M9.25 20h5.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          </svg>
        </span>
        <div className="call-title">
          <div className="takes-head">
            <h2 id="call-h">Live call</h2>
            <span className="api api-wait">Not available</span>
          </div>
          <p className="muted small">Converted voice calling is not enabled yet</p>
        </div>
      </div>
      <div className="call-notice">
        <strong>Calling is disabled to protect your audio.</strong>
        <p className="status">
          The current OpenVoice adapter converts complete WAV files; it does not provide stateful streaming inference.
        </p>
        <p className="muted small">
          On this CPU, actual-model offline tests took a median 2.078 s for each 2 s window (1.75 s stride), and
          40.423 s for each 5 s window (4 s stride). Processing would fall behind incoming audio. These runs used
          synthetic non-speech input, so intelligibility, voice similarity, and audible continuity are unverified.
          There is no signaling or WebRTC converted-audio path, and your microphone will never be sent unconverted.
        </p>
      </div>
    </section>
  );
}
