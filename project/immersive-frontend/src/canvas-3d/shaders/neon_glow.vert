// Shader de vértices — efecto de brillo neón para objetos destacados
// por el pedagogical_agent (priority: "high"). No compilado/ejecutado
// en este entorno (requiere contexto WebGL real en navegador).
varying vec3 vNormal;
varying vec3 vPosition;

void main() {
  vNormal = normalize(normalMatrix * normal);
  vPosition = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
