import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiService } from "../services/api";

export const Header: React.FC = () => {
  const location = useLocation();
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    const checkApi = async () => {
      const health = await apiService.checkHealth();
      if (mounted) {
        setApiOnline(!health.isMock && health.status === "healthy");
      }
    };
    checkApi();
    const interval = setInterval(checkApi, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const navItems = [
    { label: "Incident", path: "/" },
    { label: "Ingest", path: "/ingest" },
    { label: "Pipeline", path: "/pipeline" },
    { label: "Diagnosis", path: "/diagnosis" },
    { label: "Runbook", path: "/runbook" },
    { label: "Telemetry", path: "/telemetry" },
    { label: "Vault", path: "/vault" },
  ];

  return (
    <header className="site-header">
      <Link to="/" className="brand">
        <span className="brand-mark" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="9" />
            <line x1="12" y1="3" x2="12" y2="7" />
            <line x1="12" y1="17" x2="12" y2="21" />
            <line x1="3" y1="12" x2="7" y2="12" />
            <line x1="17" y1="12" x2="21" y2="12" />
          </svg>
        </span>
        <span className="brand-word">NetCoop</span>
        <span className="brand-meta">NOC / ISSUE 13</span>
      </Link>

      <nav className="site-nav">
        {navItems.map((item, idx) => {
          const isActive = location.pathname === item.path;
          return (
            <Link key={item.path} to={item.path} className={`nav-link ${isActive ? "active" : ""}`}>
              <span className="nav-index">0{idx + 1}</span>
              <span className="roll" data-text={item.label}>
                <span>{item.label}</span>
              </span>
            </Link>
          );
        })}

        <div
          title={apiOnline ? "FastAPI Backend Online (http://127.0.0.1:8000)" : "Local Autonomous Mode"}
          className={`api-status ${apiOnline ? "is-online" : ""}`}
        >
          <span className="api-dot" />
          <span>{apiOnline ? "online" : "offline"}</span>
        </div>
      </nav>
    </header>
  );
};
