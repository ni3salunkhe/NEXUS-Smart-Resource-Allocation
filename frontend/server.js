import express from 'express';
import { createProxyMiddleware, fixRequestBody } from 'http-proxy-middleware';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PROXY_PORT || 3001;
const TARGET_API = process.env.API_URL || 'http://localhost:8000';

app.use(cors({ origin: 'http://localhost:3000', credentials: true }));
app.use(cookieParser());
app.use(express.json());
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
  next();
});

// Helper to set httpOnly cookie for refresh token
const setRefreshCookie = (res, refreshToken) => {
  res.cookie('refresh_token', refreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
  });
};

app.post('/proxy/auth/login', async (req, res) => {
  try {
    const response = await fetch(`${SERVICES.auth}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    
    if (!response.ok) {
      const text = await response.text();
      try {
        return res.status(response.status).json(JSON.parse(text));
      } catch (e) {
        return res.status(response.status).json({ detail: text || "Authentication error" });
      }
    }
    
    const data = await response.json();
    setRefreshCookie(res, data.refresh_token);
    
    // Do not send refresh_token to client
    delete data.refresh_token;
    res.json(data);
  } catch (error) {
    res.status(500).json({ detail: 'Internal Server Error' });
  }
});

app.post('/proxy/auth/refresh', async (req, res) => {
  const refreshToken = req.cookies.refresh_token;
  if (!refreshToken) return res.status(401).json({ detail: 'No refresh token' });

  try {
    const response = await fetch(`${SERVICES.auth}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    });

    if (!response.ok) {
      const text = await response.text();
      try {
        return res.status(response.status).json(JSON.parse(text));
      } catch (e) {
        return res.status(response.status).json({ detail: text || "Refresh error" });
      }
    }

    const data = await response.json();
    setRefreshCookie(res, data.refresh_token);
    
    delete data.refresh_token;
    res.json(data);
  } catch (error) {
    res.status(500).json({ detail: 'Internal Server Error' });
  }
});

app.post('/proxy/auth/logout', async (req, res) => {
  const refreshToken = req.cookies.refresh_token;
  if (refreshToken) {
    try {
      await fetch(`${SERVICES.auth}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken })
      });
    } catch (e) {
      // Ignore errors on logout
    }
  }
  res.clearCookie('refresh_token');
  res.status(200).json({ success: true });
});

app.post('/proxy/logs', (req, res) => {
  const { level, message, stack, url, userAgent, timestamp } = req.body;
  const logDir = path.join(__dirname, 'logs');
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }

  const logFile = path.join(logDir, 'frontend_err.log');
  const logEntry = JSON.stringify({
    timestamp: timestamp || new Date().toISOString(),
    level: level || 'ERROR',
    message,
    url,
    userAgent,
    stack
  }) + '\n';

  fs.appendFile(logFile, logEntry, (err) => {
    if (err) {
      console.error('Failed to write to frontend log file:', err);
      return res.status(500).json({ detail: 'Failed to write log' });
    }
    res.status(204).send();
  });
});

// Proxy configuration for local development routing
const SERVICES = {
  auth: 'http://localhost:8000',
  registry: 'http://localhost:8001',
  ingestion: 'http://localhost:8002',
  coordination: 'http://localhost:8003',
  intelligence: 'http://localhost:8004',
  analytics: 'http://localhost:8005',
};

// Map /proxy/auth directly to Auth service
app.use('/proxy/auth', createProxyMiddleware({
  target: SERVICES.auth,
  changeOrigin: true,
  pathRewrite: (path) => '/auth' + path,
  on: { proxyReq: fixRequestBody },
}));

// Route API prefixes to correct microservices
app.use('/api/auth', createProxyMiddleware({ target: SERVICES.auth, changeOrigin: true, pathRewrite: { '^/api/auth': '' }, on: { proxyReq: fixRequestBody } }));
app.use('/api/registry', createProxyMiddleware({ target: SERVICES.registry, changeOrigin: true, pathRewrite: { '^/api/registry': '' }, on: { proxyReq: fixRequestBody } }));
app.use('/api/ingestion', createProxyMiddleware({ target: SERVICES.ingestion, changeOrigin: true, pathRewrite: { '^/api/ingestion': '' }, on: { proxyReq: fixRequestBody } }));
app.use('/api/coordination', createProxyMiddleware({ target: SERVICES.coordination, changeOrigin: true, pathRewrite: { '^/api/coordination': '' }, on: { proxyReq: fixRequestBody } }));
app.use('/api/intelligence', createProxyMiddleware({ target: SERVICES.intelligence, changeOrigin: true, pathRewrite: { '^/api/intelligence': '' }, on: { proxyReq: fixRequestBody } }));
app.use('/api/analytics', createProxyMiddleware({ target: SERVICES.analytics, changeOrigin: true, pathRewrite: { '^/api/analytics': '' }, on: { proxyReq: fixRequestBody } }));

// Fallback for generic /proxy/ endpoints (e.g. /proxy/tenants -> /tenants on auth)
app.use('/proxy', createProxyMiddleware({
  target: SERVICES.auth,
  changeOrigin: true,
  pathRewrite: { '^/proxy': '' },
  on: { proxyReq: fixRequestBody },
}));

// Catch-all for debugging 404s
app.use((req, res) => {
  console.log(`[404] - ${req.method} ${req.url}`);
  res.status(404).json({ detail: `Route ${req.method} ${req.url} not found on proxy` });
});

app.listen(PORT, () => {
  console.log(`Proxy server running on port ${PORT}`);
});
