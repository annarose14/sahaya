import React, { Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Family from "./pages/Family.jsx";
import Done from "./pages/Done.jsx";
import "./styles.css";

// The dashboard (with AG Grid) loads only when opened, so the shopping page stays light.
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));

const path = window.location.pathname;
const Page = path.startsWith("/dashboard") ? Dashboard : path.startsWith("/family") ? Family
  : path.startsWith("/done") ? Done : App;

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Suspense fallback={<p className="shell lead">Loading…</p>}>
      <Page />
    </Suspense>
  </React.StrictMode>
);
