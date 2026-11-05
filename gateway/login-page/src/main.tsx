import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { LoginPage } from "./components/LoginPage";
import { readDestination } from "./destination";

const container = document.getElementById("root");
if (!container) throw new Error("#root element is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <LoginPage destination={readDestination(window.location.search)} />
  </StrictMode>,
);
