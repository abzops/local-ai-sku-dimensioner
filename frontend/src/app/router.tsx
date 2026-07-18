import { Route, Routes } from "react-router-dom";

import { AppNavigation } from "../components/AppNavigation";
import { CalibrationPage } from "../pages/CalibrationPage";
import { HistoryPage } from "../pages/HistoryPage";
import { HomePage } from "../pages/HomePage";
import { MeasurementResultPage } from "../pages/MeasurementResultPage";
import { NewScanPage } from "../pages/NewScanPage";
import { ScanDetailPage } from "../pages/ScanDetailPage";

export function AppRoutes() {
  return (
    <>
      <AppNavigation />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/status" element={<HomePage />} />
        <Route path="/scans/new" element={<NewScanPage />} />
        <Route path="/scans" element={<HistoryPage />} />
        <Route path="/scans/:scanId" element={<ScanDetailPage />} />
        <Route
          path="/scans/:scanId/measurements/:measurementId"
          element={<MeasurementResultPage />}
        />
        <Route path="/calibration" element={<CalibrationPage />} />
      </Routes>
    </>
  );
}
