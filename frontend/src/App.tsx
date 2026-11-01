import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import Lenis from "lenis";

import { Cursor } from "./components/Cursor";
import { Header } from "./components/Header";
import { ScrollProgress } from "./components/ScrollProgress";

import { Home } from "./pages/Home";
import { Ingest } from "./pages/Ingest";
import { Pipeline } from "./pages/Pipeline";
import { Diagnosis } from "./pages/Diagnosis";
import { Runbook } from "./pages/Runbook";
import { Telemetry } from "./pages/Telemetry";
import { Vault } from "./pages/Vault";

const AnimatedRoutes: React.FC = () => {
  const location = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Home />} />
        <Route path="/ingest" element={<Ingest />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/diagnosis" element={<Diagnosis />} />
        <Route path="/runbook" element={<Runbook />} />
        <Route path="/telemetry" element={<Telemetry />} />
        <Route path="/vault" element={<Vault />} />
      </Routes>
    </AnimatePresence>
  );
};

export const App: React.FC = () => {
  useEffect(() => {
    // Initialize Lenis smooth scroll engine
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      orientation: "vertical",
      gestureOrientation: "vertical",
      smoothWheel: true,
      touchMultiplier: 2,
    });

    function raf(time: number) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    const rafId = requestAnimationFrame(raf);

    return () => {
      cancelAnimationFrame(rafId);
      lenis.destroy();
    };
  }, []);

  return (
    <BrowserRouter>
      <Cursor />
      <ScrollProgress />
      <Header />
      <main>
        <AnimatedRoutes />
      </main>
    </BrowserRouter>
  );
};

export default App;
