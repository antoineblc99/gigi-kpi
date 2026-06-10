/**
 * GET /op/<key> — porte d'entrée du mode opérateur.
 * key === DECISION_ACT_SECRET → cookie httpOnly 30 j + redirect /.
 * Sinon : 404 (indistinguable d'une page inexistante).
 */
import { NextResponse } from "next/server";
import { OP_COOKIE, opHash } from "@/lib/op";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ key: string }> }
) {
  const { key } = await params;
  const secret = process.env.DECISION_ACT_SECRET;
  if (!secret || key !== secret) {
    return new NextResponse("Not found", { status: 404 });
  }

  const res = NextResponse.redirect(new URL("/", req.url));
  res.cookies.set(OP_COOKIE, opHash()!, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 jours
  });
  return res;
}
