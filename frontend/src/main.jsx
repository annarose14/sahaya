import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Family from "./pages/Family.jsx";
import Done from "./pages/Done.jsx";
import "./styles.css";

const path = window.location.pathname;
const Page = path.startsWith("/family") ? Family : path.startsWith("/done") ? Done : App;

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Page />
  </React.StrictMode>
);
