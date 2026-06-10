export default function Loading() {
  return (
    <main className="container">
      <div className="skel" style={{ height: 90, marginBottom: 24 }} />
      <div className="skel" style={{ height: 110, marginBottom: 24 }} />
      <div className="skel" style={{ height: 260, marginBottom: 24 }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        <div className="skel" style={{ height: 120 }} />
        <div className="skel" style={{ height: 120 }} />
        <div className="skel" style={{ height: 120 }} />
      </div>
    </main>
  );
}
