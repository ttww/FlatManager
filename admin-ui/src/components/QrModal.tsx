import QRCode from "qrcode";
import { useEffect, useRef } from "react";

type Props = {
  url: string;
  apartmentId: string;
  onClose: () => void;
};

export function QrModal({ url, apartmentId, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (canvasRef.current) {
      void QRCode.toCanvas(canvasRef.current, url, {
        width: 280,
        margin: 2,
        color: { dark: "#1f2f2a", light: "#ffffff" },
      });
    }
  }, [url]);

  const onDownload = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = `qr-${apartmentId}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  };

  const onBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onBackdropClick}>
      <div className="modal-box">
        <div className="modal-header">
          <h3>Guest Link QR — {apartmentId}</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <canvas ref={canvasRef} />

        <p className="modal-url">{url}</p>

        <div className="modal-actions">
          <button type="button" onClick={() => { void navigator.clipboard.writeText(url); }}>
            Copy Link
          </button>
          <button type="button" className="primary-button" onClick={onDownload}>
            Download PNG
          </button>
        </div>
      </div>
    </div>
  );
}
