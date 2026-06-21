import { Navigate, Route, Routes } from "react-router-dom";

import "./guest.css";
import { GuestOpenPage } from "./pages/GuestOpenPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<GuestOpenPage />} />
      <Route path="/open" element={<GuestOpenPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
