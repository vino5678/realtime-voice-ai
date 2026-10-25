import { useEffect, useRef, useState } from 'react';

interface Props {
  analyser: AnalyserNode | null;
  recording: boolean;
}

const toDb = (x: number) => 20 * Math.log10(Math.max(x, 1e-9));

export function Waveform({ analyser, recording }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [peakDb, setPeakDb] = useState<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const g = canvas.getContext('2d');
    if (!g) return;
    const data = analyser ? new Float32Array(analyser.fftSize) : null;
    let raf = 0;
    let lastReadout = 0;

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const d = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(r.width * d));
      canvas.height = Math.max(1, Math.round(r.height * d));
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const draw = (t: number) => {
      const { width: w, height: h } = canvas;
      g.clearRect(0, 0, w, h);
      g.lineWidth = Math.max(1, (window.devicePixelRatio || 1) * 1.5);

      // centre line
      g.strokeStyle = 'rgba(160, 190, 200, 0.25)';
      g.beginPath();
      g.moveTo(0, h / 2);
      g.lineTo(w, h / 2);
      g.stroke();

      if (analyser && data) {
        analyser.getFloatTimeDomainData(data);
        let peak = 0;
        g.strokeStyle = recording ? '#FF7A6B' : '#62D6CB';
        g.beginPath();
        for (let i = 0; i < data.length; i++) {
          const v = data[i];
          if (Math.abs(v) > peak) peak = Math.abs(v);
          const x = (i / (data.length - 1)) * w;
          const y = h / 2 - v * (h / 2) * 0.95;
          if (i === 0) g.moveTo(x, y);
          else g.lineTo(x, y);
        }
        g.stroke();
        if (t - lastReadout > 120) {
          setPeakDb(toDb(peak));
          lastReadout = t;
        }
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [analyser, recording]);

  const live = analyser !== null;
  const hot = live && peakDb !== null && peakDb > -1;

  return (
    <div className="scope">
      <canvas ref={canvasRef} className="scope-canvas" role="img" aria-label="Live microphone waveform" />
      {!live && <p className="scope-idle">Enable the microphone to see your voice here.</p>}
      {live && (
        <p className={`scope-readout${hot ? ' is-hot' : ''}`} aria-live="off">
          {hot ? 'Too loud: move back from the mic' : peakDb !== null && peakDb > -100 ? `Peak ${peakDb.toFixed(0)} dBFS` : 'Listening'}
        </p>
      )}
    </div>
  );
}
