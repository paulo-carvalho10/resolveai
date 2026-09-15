import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";

import { useAuth } from "./auth/AuthProvider";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { AdminPage } from "./pages/AdminPage";
import { ArticlePage } from "./pages/ArticlePage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { LoginPage } from "./pages/LoginPage";
import { NewTicketPage } from "./pages/NewTicketPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { TicketsPage } from "./pages/TicketsPage";

// The charting library is only needed on the dashboard, so it loads with it.
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })),
);

export function App() {
  const { user, loading, isStaff, isAdmin } = useAuth();

  if (loading) return <Spinner label="Carregando sua sessão..." />;
  if (!user) return <LoginPage />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route
          path="/"
          element={
            isStaff ? (
              <Suspense fallback={<Spinner label="Carregando indicadores..." />}>
                <DashboardPage />
              </Suspense>
            ) : (
              <Navigate to="/chamados" replace />
            )
          }
        />
        <Route path="/chamados" element={<TicketsPage />} />
        <Route path="/chamados/novo" element={<NewTicketPage />} />
        <Route path="/chamados/:id" element={<TicketDetailPage />} />
        <Route path="/base-de-conhecimento" element={<KnowledgePage />} />
        <Route path="/base-de-conhecimento/:id" element={<ArticlePage />} />
        <Route
          path="/administracao"
          element={isAdmin ? <AdminPage /> : <Navigate to="/chamados" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
