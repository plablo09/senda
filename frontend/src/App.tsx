import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Inicio } from "./pages/Inicio";
import { Editor } from "./pages/Editor";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Inicio />} />
        <Route path="/editor" element={<Editor />} />
        <Route path="/editor/:id" element={<Editor />} />
      </Routes>
    </BrowserRouter>
  );
}
