'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Live crawlers is the landing screen. */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/live');
  }, [router]);

  return null;
}
