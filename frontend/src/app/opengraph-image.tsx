import { ImageResponse } from "next/og";

export const alt = "ERETZ Propiedades — encontrá propiedades en Argentina";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        alignItems: "center",
        background: "linear-gradient(135deg, #06192f 0%, #0d3864 70%, #2166a5 100%)",
        color: "white",
        display: "flex",
        height: "100%",
        justifyContent: "center",
        padding: "72px",
        width: "100%",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", maxWidth: 980 }}>
        <div style={{ color: "#d6b66f", display: "flex", fontSize: 30, fontWeight: 800, letterSpacing: 8 }}>ERETZ PROPIEDADES</div>
        <div style={{ display: "flex", fontSize: 74, fontWeight: 900, letterSpacing: -3, lineHeight: 1.06, marginTop: 28 }}>
          Encontrá propiedades en el mapa
        </div>
        <div style={{ color: "#dceaf6", display: "flex", fontSize: 30, lineHeight: 1.4, marginTop: 30 }}>
          Inventario real de Argentina · contacto directo con el publicador
        </div>
      </div>
    </div>,
    size,
  );
}
