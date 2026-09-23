// Shader de fragmentos — color e intensidad del brillo neón.
// No compilado/ejecutado en este entorno (requiere contexto WebGL real).
varying vec3 vNormal;
varying vec3 vPosition;

uniform vec3 glowColor;
uniform float intensity;

void main() {
  float rim = 1.0 - max(dot(normalize(vNormal), vec3(0.0, 0.0, 1.0)), 0.0);
  vec3 color = glowColor * (rim * intensity + 0.2);
  gl_FragColor = vec4(color, 1.0);
}
