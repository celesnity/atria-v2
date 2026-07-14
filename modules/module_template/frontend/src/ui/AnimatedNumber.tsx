import { useEffect, useState } from "react";
import { useMotionValue, animate } from "motion/react";

export default function AnimatedNumber({ value }: { value: number }) {
  const mv = useMotionValue(0);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.8, ease: "easeOut" });
    const unsub = mv.on("change", (v) => setDisplay(Math.round(v)));
    return () => { controls.stop(); unsub(); };
  }, [value]);

  return <span>{display}</span>;
}
