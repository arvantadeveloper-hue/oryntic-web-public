import React, { useState } from "react";
import { Images } from "lucide-react";
import { GalleryGrid, GalleryFilterBar } from "../components/Gallery";

export default function Gallery() {
  const [type, setType] = useState("all");
  return (
    <div className="mx-auto max-w-6xl p-5 sm:p-8 fade-up" data-testid="gallery-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 sm:text-3xl"><Images size={26} className="text-[#2F6BFF]" /> Galeri</h1>
          <p className="mt-1 text-sm text-slate-500">Semua dokumen, gambar, dan video yang dibuat asisten Anda. Buka, unduh, atau lampirkan kembali ke chat tanpa upload ulang.</p>
        </div>
        <GalleryFilterBar value={type} onChange={setType} />
      </div>
      <div className="mt-6"><GalleryGrid type={type} /></div>
    </div>
  );
}
