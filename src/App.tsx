/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { 
  Menu, 
  Scan, 
  Settings, 
  Home, 
  Download, 
  Eye, 
  CheckCircle2, 
  AlertCircle, 
  ArrowRight, 
  Plus, 
  Search, 
  Calendar, 
  Filter, 
  MoreVertical, 
  Delete, 
  ChevronLeft, 
  ChevronRight,
  X,
  HelpCircle,
  Sun,
  Maximize,
  ZoomIn,
  ZoomOut,
  Type,
  SquareCheck,
  MousePointer2,
  Flashlight
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

type Screen = 'HOME' | 'SCAN' | 'REVIEW' | 'TEMPLATE' | 'DATASET';

export default function App() {
  const [currentScreen, setCurrentScreen] = useState<Screen>('HOME');

  const renderScreen = () => {
    switch (currentScreen) {
      case 'HOME':
        return <Dashboard onNavigate={setCurrentScreen} />;
      case 'SCAN':
        return <Scanner onNavigate={setCurrentScreen} />;
      case 'REVIEW':
        return <Review onNavigate={setCurrentScreen} />;
      case 'TEMPLATE':
        return <TemplateBuilder onNavigate={setCurrentScreen} />;
      case 'DATASET':
        return <DatasetView onNavigate={setCurrentScreen} />;
      default:
        return <Dashboard onNavigate={setCurrentScreen} />;
    }
  };

  return (
    <div className="min-h-screen bg-surface text-on-surface pb-24 md:pb-0">
      <Header onNavigate={setCurrentScreen} currentScreen={currentScreen} />
      
      <main className="max-w-7xl mx-auto">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentScreen}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {renderScreen()}
          </motion.div>
        </AnimatePresence>
      </main>

      <BottomNav currentScreen={currentScreen} onNavigate={setCurrentScreen} />
    </div>
  );
}

// --- Components ---

function Header({ onNavigate, currentScreen }: { onNavigate: (s: Screen) => void, currentScreen: Screen }) {
  return (
    <header className="fixed top-0 w-full z-50 bg-slate-50/80 backdrop-blur-xl flex justify-between items-center px-6 h-16 border-b border-slate-200/20">
      <div className="flex items-center gap-4">
        <button className="p-2 text-primary hover:bg-slate-100 rounded-xl transition-colors">
          <Menu size={24} />
        </button>
        <h1 
          className="text-xl font-black text-primary tracking-tight cursor-pointer"
          onClick={() => onNavigate('HOME')}
        >
          Survey Digitizer
        </h1>
      </div>
      <div className="flex items-center gap-3">
        {currentScreen === 'REVIEW' && (
          <span className="text-[10px] font-bold tracking-widest uppercase text-on-surface-variant px-3 py-1 bg-surface-container-low rounded-full">
            Review Mode
          </span>
        )}
        <div className="w-8 h-8 rounded-full overflow-hidden border-2 border-primary/10">
          <img 
            src="https://picsum.photos/seed/analyst/100/100" 
            alt="User Profile" 
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover"
          />
        </div>
      </div>
    </header>
  );
}

function BottomNav({ currentScreen, onNavigate }: { currentScreen: Screen, onNavigate: (s: Screen) => void }) {
  const navItems: { screen: Screen; icon: any; label: string }[] = [
    { screen: 'HOME', icon: Home, label: 'Home' },
    { screen: 'SCAN', icon: Scan, label: 'Scans' },
    { screen: 'DATASET', icon: Settings, label: 'Settings' }, // Using Dataset for settings placeholder per screenshot
  ];

  return (
    <nav className="fixed bottom-0 left-0 w-full flex justify-around items-center px-4 pb-6 pt-3 bg-slate-50/80 backdrop-blur-xl z-50 border-t border-slate-200/20 shadow-lg md:hidden">
      {navItems.map((item) => (
        <button
          key={item.screen}
          onClick={() => onNavigate(item.screen)}
          className={`flex flex-col items-center justify-center rounded-xl px-4 py-1 transition-all active:scale-90 ${
            currentScreen === item.screen 
              ? 'bg-blue-100/50 text-primary' 
              : 'text-slate-500 hover:text-primary'
          }`}
        >
          <item.icon size={24} fill={currentScreen === item.screen ? "currentColor" : "none"} />
          <span className="text-[10px] font-bold uppercase tracking-widest mt-1">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}

// --- Screens ---

function Dashboard({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  return (
    <div className="pt-24 px-6 space-y-8 pb-12">
      {/* Hero Section */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 bg-gradient-to-br from-primary to-primary-container p-8 rounded-xl flex flex-col justify-between min-h-[240px] relative overflow-hidden group shadow-lg">
          <div className="relative z-10">
            <h2 className="text-on-primary text-3xl font-bold tracking-tight mb-2">Digitize New Dataset</h2>
            <p className="text-on-primary/80 max-w-md font-medium">
              Upload paper surveys or capture images to convert physical data into structured CSV/Excel formats using our OCR engine.
            </p>
          </div>
          <div className="mt-8 flex gap-3 relative z-10">
            <button 
              onClick={() => onNavigate('SCAN')}
              className="bg-surface-container-lowest text-primary px-8 py-3 rounded-xl font-bold flex items-center gap-2 hover:bg-surface-bright transition-colors active:scale-95"
            >
              <Scan size={20} />
              Scan New Form
            </button>
            <button className="bg-primary-container/30 text-on-primary border border-on-primary/20 backdrop-blur-md px-6 py-3 rounded-xl font-bold hover:bg-primary-container/50 transition-colors">
              Bulk Upload
            </button>
          </div>
          <Scan className="absolute -right-8 -bottom-8 w-48 h-48 text-white/5 pointer-events-none group-hover:scale-110 transition-transform duration-700" />
        </div>

        {/* Stats */}
        <div className="grid grid-rows-2 gap-4">
          <div className="bg-surface-container-low p-6 rounded-xl flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Total Forms Digitized</span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-primary tracking-tighter">1,240</span>
              <span className="text-xs font-bold text-tertiary">+12% this month</span>
            </div>
          </div>
          <div className="bg-surface-container-low p-6 rounded-xl flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Pending Review</span>
            <div className="flex items-center justify-between">
              <span className="text-4xl font-black text-on-surface tracking-tighter">12</span>
              <div className="bg-tertiary-container/20 text-tertiary-container px-3 py-1 rounded-full text-xs font-bold">
                Action Required
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Recent Datasets */}
        <section className="lg:col-span-8 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-black text-on-surface tracking-tight">Recent Datasets</h3>
            <button 
              onClick={() => onNavigate('DATASET')}
              className="text-sm font-bold text-primary hover:underline"
            >
              View All
            </button>
          </div>
          <div className="space-y-3">
            {[
              { title: 'Health Survey 2024', meta: 'Modified 2h ago • 450 Entries', icon: 'medical', color: 'bg-secondary-container' },
              { title: 'Customer Feedback Q3', meta: 'Modified Yesterday • 890 Entries', icon: 'smile', color: 'bg-primary-fixed' },
              { title: 'Urban Planning Census', meta: 'Modified 3 days ago • 120 Entries', icon: 'building', color: 'bg-tertiary-fixed' },
            ].map((item, i) => (
              <div key={i} className="group bg-surface-container-lowest p-5 rounded-xl flex items-center justify-between hover:bg-white transition-all hover:shadow-md cursor-pointer">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 ${item.color} flex items-center justify-center rounded-xl text-on-secondary-container`}>
                    <Plus size={24} />
                  </div>
                  <div>
                    <h4 className="font-bold text-on-surface">{item.title}</h4>
                    <p className="text-xs font-medium text-on-surface-variant">{item.meta}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button className="p-2 text-on-surface-variant hover:text-primary hover:bg-primary/5 rounded-lg transition-colors">
                    <Eye size={20} />
                  </button>
                  <button className="bg-surface-container-high text-on-surface-variant px-4 py-2 rounded-xl text-xs font-bold hover:bg-primary-container hover:text-on-primary transition-colors flex items-center gap-2">
                    <Download size={14} />
                    Export CSV
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Recent Projects / Activity */}
        <section className="lg:col-span-4 space-y-6">
          <h3 className="text-xl font-black text-on-surface tracking-tight">Recent Projects</h3>
          <div className="bg-surface-container-low rounded-xl p-6 space-y-6">
            <div className="relative pl-6 border-l-2 border-primary/20 space-y-8">
              {[
                { title: 'Batch Processing Complete', sub: 'Project: "Annual Logistics Review"', time: 'Just Now', color: 'bg-primary' },
                { title: '12 Conflicts Detected', sub: 'Manual verification needed for handwritten signatures.', time: '2 HOURS AGO', color: 'bg-tertiary' },
                { title: 'New Template Created', sub: 'Custom parser for "NPS Feedback Cards" is ready.', time: 'YESTERDAY', color: 'bg-outline' },
              ].map((activity, i) => (
                <div key={i} className="relative">
                  <div className={`absolute -left-[31px] top-0 w-4 h-4 rounded-full ${activity.color} ring-4 ring-surface-container-low`}></div>
                  <div className="space-y-1">
                    <p className="text-sm font-bold text-on-surface">{activity.title}</p>
                    <p className="text-xs text-on-surface-variant">{activity.sub}</p>
                    <p className="text-[10px] font-bold text-primary-container uppercase mt-2">{activity.time}</p>
                  </div>
                </div>
              ))}
            </div>
            <button className="w-full py-3 bg-surface-container-high rounded-xl text-xs font-bold text-primary hover:bg-primary/5 transition-colors">
              View Full Audit Log
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

function Scanner({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  return (
    <div className="fixed inset-0 bg-on-background z-[60] flex flex-col overflow-hidden">
      {/* Top Nav */}
      <nav className="absolute top-0 w-full z-50 flex justify-between items-center px-6 h-20 bg-gradient-to-b from-black/60 to-transparent">
        <button 
          onClick={() => onNavigate('HOME')}
          className="w-10 h-10 flex items-center justify-center rounded-full bg-white/10 backdrop-blur-md text-white active:scale-95"
        >
          <X size={24} />
        </button>
        <div className="flex items-center gap-2 bg-white/10 backdrop-blur-md px-4 py-1.5 rounded-full">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          <span className="text-[10px] font-bold uppercase tracking-widest text-white">Live Engine Active</span>
        </div>
        <button className="w-10 h-10 flex items-center justify-center rounded-full bg-white/10 backdrop-blur-md text-white">
          <HelpCircle size={24} />
        </button>
      </nav>

      {/* Viewfinder */}
      <div className="relative flex-grow flex items-center justify-center">
        <img 
          src="https://picsum.photos/seed/form/800/1200" 
          alt="Camera View" 
          referrerPolicy="no-referrer"
          className="absolute inset-0 w-full h-full object-cover opacity-60 brightness-75"
        />
        
        <div className="relative z-10 w-full max-w-md aspect-[3/4] mx-6">
          <div className="absolute inset-0 border-2 border-dashed border-white/40 rounded-xl flex items-center justify-center">
            <div className="text-white/80 bg-black/40 backdrop-blur-sm px-6 py-2 rounded-full font-bold text-xs uppercase tracking-tighter">
              Align form here
            </div>
          </div>
          {/* Corner Brackets */}
          <div className="absolute -top-2 -left-2 w-12 h-12 border-t-4 border-l-4 border-primary rounded-tl-xl shadow-lg"></div>
          <div className="absolute -top-2 -right-2 w-12 h-12 border-t-4 border-r-4 border-primary rounded-tr-xl shadow-lg"></div>
          <div className="absolute -bottom-2 -left-2 w-12 h-12 border-b-4 border-l-4 border-primary rounded-bl-xl shadow-lg"></div>
          <div className="absolute -bottom-2 -right-2 w-12 h-12 border-b-4 border-r-4 border-primary rounded-br-xl shadow-lg"></div>
        </div>

        {/* Status Indicators */}
        <div className="absolute top-24 left-0 w-full flex justify-center gap-3 z-20">
          <div className="flex items-center gap-2 bg-black/60 backdrop-blur-xl border border-white/10 px-4 py-2 rounded-xl">
            <Sun size={14} className="text-green-400" />
            <span className="text-xs font-bold text-white tracking-tight">Lighting: Good</span>
          </div>
          <div className="flex items-center gap-2 bg-black/60 backdrop-blur-xl border border-white/10 px-4 py-2 rounded-xl">
            <Maximize size={14} className="text-blue-400" />
            <span className="text-xs font-bold text-white tracking-tight">Focus: Locked</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="relative z-50 px-8 pb-10 pt-12 bg-gradient-to-t from-black via-black/80 to-transparent">
        <div className="max-w-md mx-auto flex items-center justify-between">
          <div 
            onClick={() => onNavigate('REVIEW')}
            className="relative cursor-pointer group"
          >
            <div className="w-14 h-14 rounded-xl overflow-hidden border-2 border-white/20 group-hover:border-primary transition-all">
              <img src="https://picsum.photos/seed/thumb/100/100" alt="Last capture" referrerPolicy="no-referrer" />
            </div>
            <div className="absolute -top-2 -right-2 bg-primary text-white text-[10px] w-5 h-5 flex items-center justify-center rounded-full font-bold">1</div>
          </div>

          <button 
            onClick={() => onNavigate('REVIEW')}
            className="relative w-20 h-20 rounded-full bg-white flex items-center justify-center shadow-2xl active:scale-90 transition-transform"
          >
            <div className="w-[72px] h-[72px] rounded-full border-2 border-black/5"></div>
          </button>

          <button className="w-14 h-14 flex items-center justify-center rounded-full bg-white/10 backdrop-blur-md text-white active:bg-white active:text-black transition-all">
            <Flashlight size={24} />
          </button>
        </div>

        <div className="mt-8 flex justify-center gap-8">
          <button className="text-xs font-black uppercase tracking-[0.2em] text-white">Document</button>
          <button className="text-xs font-black uppercase tracking-[0.2em] text-white/40">Multi-page</button>
          <button className="text-xs font-black uppercase tracking-[0.2em] text-white/40">QR Code</button>
        </div>
      </footer>
    </div>
  );
}

function Review({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  return (
    <div className="pt-24 px-4 md:px-8 pb-32">
      <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold tracking-tight text-on-surface leading-none">Review Data Extraction</h2>
          <p className="mt-2 text-on-surface-variant font-medium">Scan ID: #OCR-88291 • Yoga Community Survey</p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-surface-container-low rounded-xl border border-outline-variant/15">
          <span className="w-3 h-3 rounded-full bg-error animate-pulse"></span>
          <span className="text-sm font-bold text-on-surface">3 Low Confidence Fields</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Field: Name */}
        <div className="flex flex-col bg-surface-container-low rounded-xl overflow-hidden group">
          <div className="p-4 bg-surface-container-lowest">
            <div className="flex justify-between items-center mb-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Original Input: Name</span>
              <span className="text-[10px] font-bold px-2 py-0.5 bg-green-100 text-green-800 rounded-full">98% Confidence</span>
            </div>
            <div className="h-24 bg-white rounded-lg flex items-center justify-center p-2 border border-outline-variant/10 overflow-hidden">
              <img src="https://picsum.photos/seed/name/400/100" alt="Handwritten name" referrerPolicy="no-referrer" className="max-w-full h-auto" />
            </div>
          </div>
          <div className="p-5 space-y-3">
            <label className="block text-xs font-bold text-on-surface-variant uppercase tracking-wider">Extracted Text</label>
            <input 
              className="w-full bg-surface-container-highest border-0 border-b-2 border-transparent focus:border-primary focus:ring-0 rounded-t-lg font-medium text-on-surface transition-all" 
              type="text" 
              defaultValue="Jonathan Reed" 
            />
          </div>
        </div>

        {/* Field: Phone (Error) */}
        <div className="flex flex-col bg-error-container/30 rounded-xl overflow-hidden group border-2 border-error/20">
          <div className="p-4 bg-surface-container-lowest">
            <div className="flex justify-between items-center mb-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Original Input: Phone</span>
              <span className="text-[10px] font-bold px-2 py-0.5 bg-error text-on-primary rounded-full">42% Confidence</span>
            </div>
            <div className="h-24 bg-white rounded-lg flex items-center justify-center p-2 border border-error/10 overflow-hidden">
              <img src="https://picsum.photos/seed/phone/400/100" alt="Handwritten phone" referrerPolicy="no-referrer" className="max-w-full h-auto" />
            </div>
          </div>
          <div className="p-5 space-y-3">
            <div className="flex justify-between">
              <label className="block text-xs font-bold text-error uppercase tracking-wider">Requires Verification</label>
              <AlertCircle size={16} className="text-error" />
            </div>
            <input 
              className="w-full bg-surface-container-highest border-0 border-b-2 border-error focus:border-primary focus:ring-0 rounded-t-lg font-bold text-on-surface" 
              type="text" 
              defaultValue="555-018-?23" 
            />
            <p className="text-[10px] font-medium text-on-primary bg-error px-2 py-1 rounded inline-block">OCR conflict: digit '2' could be 'z' or '7'</p>
          </div>
        </div>

        {/* Field: Checkbox */}
        <div className="flex flex-col bg-surface-container-low rounded-xl overflow-hidden">
          <div className="p-4 bg-surface-container-lowest">
            <div className="flex justify-between items-center mb-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Original Input: Yoga</span>
              <span className="text-[10px] font-bold px-2 py-0.5 bg-green-100 text-green-800 rounded-full">92% Confidence</span>
            </div>
            <div className="h-24 bg-white rounded-lg flex items-center justify-center p-2 border border-outline-variant/10 overflow-hidden">
              <img src="https://picsum.photos/seed/check/100/100" alt="Handwritten checkbox" referrerPolicy="no-referrer" className="max-w-full h-auto" />
            </div>
          </div>
          <div className="p-5 space-y-4">
            <label className="block text-xs font-bold text-on-surface-variant uppercase tracking-wider">Extracted Boolean</label>
            <div className="flex items-center justify-between p-3 bg-surface-container-highest rounded-xl">
              <span className="text-sm font-bold text-on-surface">Practice regularly?</span>
              <button className="relative inline-flex h-6 w-11 items-center rounded-full bg-primary-container">
                <span className="inline-block h-4 w-4 translate-x-6 transform rounded-full bg-white transition"></span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Action Bar */}
      <div className="fixed bottom-24 left-0 w-full px-6 z-40 pointer-events-none">
        <div className="max-w-7xl mx-auto flex justify-end pointer-events-auto">
          <button 
            onClick={() => onNavigate('DATASET')}
            className="flex items-center gap-3 bg-gradient-to-br from-primary to-primary-container text-on-primary px-8 py-4 rounded-xl shadow-lg hover:brightness-110 active:scale-95 transition-all group"
          >
            <span className="text-lg font-extrabold tracking-tight">Confirm & Append to CSV</span>
            <ArrowRight size={24} className="group-hover:translate-x-1 transition-transform" />
          </button>
        </div>
      </div>
    </div>
  );
}

function TemplateBuilder({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  return (
    <div className="pt-16 h-screen flex flex-col md:flex-row overflow-hidden">
      <aside className="w-full md:w-80 bg-surface-container-low p-6 overflow-y-auto flex-shrink-0">
        <div className="mb-8">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-4">Template Fields</h2>
          <div className="space-y-3">
            {[
              { label: 'OCR: Name', val: 'Respondent Full Name', color: 'border-primary' },
              { label: 'OCR: Phone', val: 'Contact Information', color: 'border-primary' },
              { label: 'Checkbox: Yes/No', val: 'Consent Status', color: 'border-tertiary' },
            ].map((field, i) => (
              <div key={i} className={`bg-surface-container-lowest p-4 rounded-xl border-l-4 ${field.color}`}>
                <div className="flex justify-between items-start">
                  <div>
                    <p className={`text-xs font-bold mb-1 uppercase tracking-wider ${field.color.replace('border-', 'text-')}`}>{field.label}</p>
                    <p className="text-sm font-medium text-on-surface">{field.val}</p>
                  </div>
                  <MoreVertical size={14} className="text-outline" />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-[11px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-4">Add New Field</h2>
          <div className="grid grid-cols-1 gap-3">
            <button className="flex items-center gap-3 p-4 bg-surface-container-highest hover:bg-surface-container-high transition-colors rounded-xl text-left group">
              <div className="w-10 h-10 rounded-lg bg-primary-container flex items-center justify-center text-on-primary-container">
                <Type size={20} />
              </div>
              <div>
                <p className="text-sm font-bold text-on-surface">Text (OCR)</p>
                <p className="text-[11px] text-on-surface-variant">Handwriting extraction</p>
              </div>
            </button>
            <button className="flex items-center gap-3 p-4 bg-surface-container-highest hover:bg-surface-container-high transition-colors rounded-xl text-left group">
              <div className="w-10 h-10 rounded-lg bg-tertiary-container flex items-center justify-center text-on-tertiary-container">
                <SquareCheck size={20} />
              </div>
              <div>
                <p className="text-sm font-bold text-on-surface">Checkbox</p>
                <p className="text-[11px] text-on-surface-variant">Density Detection</p>
              </div>
            </button>
          </div>
        </div>
      </aside>

      <section className="flex-grow bg-surface canvas-bg flex items-center justify-center p-8 overflow-auto relative">
        <div className="relative bg-white shadow-2xl rounded-sm border border-outline-variant/10 overflow-hidden max-w-4xl w-full">
          <img 
            src="https://picsum.photos/seed/form-scan/1200/1600" 
            alt="Captured form scan" 
            referrerPolicy="no-referrer"
            className="w-full h-auto opacity-90" 
          />
          {/* Mapping Overlays */}
          <div className="absolute top-[12%] left-[15%] w-[45%] h-[6%] bg-primary/10 border-2 border-primary rounded-sm flex items-center px-3 group cursor-pointer hover:bg-primary/20 transition-all">
            <span className="absolute -top-6 left-0 bg-primary text-on-primary text-[10px] px-2 py-0.5 font-bold rounded-t-sm uppercase tracking-tighter">OCR: Name</span>
          </div>
          <div className="absolute top-[60%] left-[20%] w-[60%] h-[15%] border-2 border-dashed border-outline-variant bg-surface/30 flex items-center justify-center group cursor-crosshair">
            <div className="text-center">
              <MousePointer2 size={24} className="text-outline mx-auto mb-1" />
              <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Click and drag to map new field</p>
            </div>
          </div>
        </div>
        <div className="absolute bottom-10 right-10 flex flex-col gap-2">
          <button className="bg-surface-container-lowest p-3 rounded-full shadow-lg text-on-surface hover:bg-surface-container transition-colors">
            <ZoomIn size={20} />
          </button>
          <button className="bg-surface-container-lowest p-3 rounded-full shadow-lg text-on-surface hover:bg-surface-container transition-colors">
            <ZoomOut size={20} />
          </button>
        </div>
      </section>
    </div>
  );
}

function DatasetView({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  return (
    <div className="pt-24 pb-32 px-4 md:px-8">
      <section className="mb-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-on-surface">Dataset View</h2>
            <p className="text-on-surface-variant mt-1 font-medium">Currently viewing <span className="text-primary font-bold">124</span> scanned entries from Q3 Field Audit.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-grow md:w-80">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-outline" />
              <input 
                className="w-full pl-10 pr-4 py-2.5 bg-surface-container-highest border-none rounded-xl focus:ring-2 focus:ring-primary transition-all text-sm font-medium" 
                placeholder="Search by name or keyword..." 
                type="text" 
              />
            </div>
            <button className="flex items-center gap-2 px-4 py-2.5 bg-surface-container-low text-on-surface-variant rounded-xl font-bold text-sm hover:bg-surface-container-high transition-colors">
              <Calendar size={16} />
              Filter by Date
            </button>
            <button className="flex items-center gap-2 px-4 py-2.5 bg-surface-container-low text-on-surface-variant rounded-xl font-bold text-sm hover:bg-surface-container-high transition-colors">
              <Filter size={16} />
              Status
            </button>
          </div>
        </div>
      </section>

      <div className="bg-surface-container-low rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-high">
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-widest text-on-surface-variant">Date Scanned</th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-widest text-on-surface-variant">Question 01</th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-widest text-on-surface-variant">Integrity</th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {[
                { name: 'Jonathan Aris', date: 'Oct 24, 2023', q1: 'YES', integrity: 98, color: 'bg-primary-fixed' },
                { name: 'Sarah Landers', date: 'Oct 23, 2023', q1: 'NO', integrity: 85, color: 'bg-secondary-fixed' },
                { name: 'Marcus Knight', date: 'Oct 23, 2023', q1: 'YES', integrity: 92, color: 'bg-tertiary-fixed' },
                { name: 'Rebecca Bloom', date: 'Oct 22, 2023', q1: 'YES', integrity: 74, color: 'bg-primary-fixed' },
              ].map((row, i) => (
                <tr key={i} className="bg-surface-container-lowest hover:bg-blue-50/30 transition-colors group">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg ${row.color} flex items-center justify-center text-primary font-bold text-xs`}>
                        {row.name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <span className="text-sm font-bold text-on-surface">{row.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-on-surface-variant font-medium">{row.date}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-black uppercase ${row.q1 === 'YES' ? 'bg-secondary-container text-on-secondary-container' : 'bg-error-container text-on-error-container'}`}>
                      {row.q1}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-surface-container rounded-full overflow-hidden">
                        <div className="h-full bg-primary" style={{ width: `${row.integrity}%` }}></div>
                      </div>
                      <span className="text-[10px] font-bold text-primary">{row.integrity}%</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-outline hover:text-primary transition-colors opacity-0 group-hover:opacity-100">
                      <MoreVertical size={18} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="px-6 py-6 bg-surface-container-low border-t border-outline-variant/10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <button className="flex items-center gap-2 text-error font-bold text-[11px] uppercase tracking-widest hover:bg-error-container/20 px-3 py-2 rounded-lg transition-colors">
            <Delete size={16} />
            Clear Dataset
          </button>
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-bold uppercase tracking-widest text-on-surface-variant mr-2">Rows per page: 10</span>
            <button className="flex items-center gap-2 bg-primary hover:bg-primary-container text-white px-6 py-3 rounded-xl font-bold text-sm shadow-sm transition-all active:scale-95">
              <Download size={16} />
              Export to CSV
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 flex justify-center md:justify-start">
        <nav className="flex items-center gap-1">
          <button className="w-10 h-10 flex items-center justify-center rounded-xl bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest transition-colors">
            <ChevronLeft size={20} />
          </button>
          <button className="w-10 h-10 flex items-center justify-center rounded-xl bg-primary text-white font-bold text-sm">1</button>
          <button className="w-10 h-10 flex items-center justify-center rounded-xl bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest transition-colors font-bold text-sm">2</button>
          <button className="w-10 h-10 flex items-center justify-center rounded-xl bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest transition-colors font-bold text-sm">3</button>
          <span className="px-2 text-outline-variant">...</span>
          <button className="w-10 h-10 flex items-center justify-center rounded-xl bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest transition-colors font-bold text-sm">12</button>
          <button className="w-10 h-10 flex items-center justify-center rounded-xl bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest transition-colors">
            <ChevronRight size={20} />
          </button>
        </nav>
      </div>
    </div>
  );
}
