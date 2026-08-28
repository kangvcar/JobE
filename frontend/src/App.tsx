import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { MePage } from "./pages/MePage";

const MarketPage = lazy(() => import("./pages/MarketPage").then((m) => ({ default: m.MarketPage })));
const GraphPage = lazy(() => import("./pages/GraphPage").then((m) => ({ default: m.GraphPage })));
const DiagnosePage = lazy(() => import("./pages/DiagnosePage").then((m) => ({ default: m.DiagnosePage })));
const ReviewPage = lazy(() => import("./pages/ReviewPage").then((m) => ({ default: m.ReviewPage })));

function Fallback() {
  return (
    <div className="px-6 py-10 text-sm text-ink-soft" role="status">
      正在打开这一页。
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Fallback />}>
        <Routes>
          <Route element={<Shell />}>
            <Route path="/" element={<MePage />} />
            <Route path="/market" element={<MarketPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/diagnose" element={<DiagnosePage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
