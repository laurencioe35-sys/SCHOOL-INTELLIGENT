import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { ClassroomListPage } from "./pages/ClassroomListPage";
import { ClassroomPage } from "./pages/ClassroomPage";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route element={<ProtectedRoute />}>
            {/* /aulas: listado real de aulas de la organización (antes no
                existía — el roomId de la pizarra estaba hardcodeado a
                "aula-demo", así que cualquier aula que crearas en el ERP
                terminaba compartiendo la misma pizarra CRDT). */}
            <Route path="/aulas" element={<ClassroomListPage />} />

            {/* /aula/:classroomId: el rol (profesor/alumno) se decide en
                ClassroomPage a partir del token, no de la URL — evita que
                un alumno simplemente cambie la URL para ver el panel de
                profesor. El classroomId sí viene de la URL porque es
                información pública dentro de la organización (cualquier
                miembro puede intentar entrar; la autorización real ocurre
                en el backend al iniciar/consultar la sesión). */}
            <Route path="/aula/:classroomId" element={<ClassroomPage />} />
          </Route>

          <Route path="/" element={<Navigate to="/aulas" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
