import { FloatingAssistantButton } from "@/components/chat/FloatingAssistantButton";
import { Navbar } from "@/components/layout/Navbar";
import { PropertyExplorer } from "@/components/property/PropertyExplorer";
import { getProperties } from "@/lib/property-service";

export async function MainLayout() {
  const { properties, source } = await getProperties({ includeSource: true });

  return (
    <div className="min-h-screen bg-[#f6f8fb]">
      <Navbar />
      <PropertyExplorer dataSource={source} properties={properties} />
      <FloatingAssistantButton />
    </div>
  );
}
