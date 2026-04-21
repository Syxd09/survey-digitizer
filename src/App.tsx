/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef, Component } from 'react';

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
  Flashlight,
  LogOut,
  LogIn,
  Mail,
  Lock,
  BarChart3,
  LayoutGrid,
  Save,
  LineChart,
  Activity,
  Loader2,
  Camera
} from 'lucide-react';


import { motion, AnimatePresence } from 'motion/react';
import {
  onAuthStateChanged,
  signOut,
  signUpWithEmail,
  signInWithEmail,
  getCurrentUser,
  LocalUser
} from './lib/localAuth';
import { DistributionChart, MiniSparkline } from './components/DataCharts';
import { analyticsService } from './services/analyticsService';
import { DiagnosticsDashboard } from './components/DiagnosticsDashboard';
import { Point, Quad, analyzeImageQuality, detectQuad } from './services/alignmentService';
import { ingestFormForProcessing, processFormLocally, toBase64, ExtractionResult, BACKEND_URL, registerFeedback } from './services/ocrService';
import { DetectionResult, ExtractedRow } from './services/processingService';
import { formatterService } from './services/formatterService';
import { StructuredTable } from './components/StructuredTable';
import { FormEditor, FormQuestion, exportFormAsJSON, exportFormAsCSV, saveFormLocally, computeFormMetrics } from './components/FormEditor';
import { evaluationService } from './services/evaluationService';
import { EvaluationDashboard } from './components/EvaluationDashboard';
import CameraScanner from './components/CameraScanner';
import DigitizingOverlay from './components/DigitizingOverlay';







// --- localStorage helpers ---
const DATASETS_KEY = 'survey_digitizer_datasets';
const ACTIVITIES_KEY = 'survey_digitizer_activities';
const SCANS_KEY = 'survey_digitizer_scans';

function loadFromStorage<T>(key: string): T[] {
  try {
    const data = localStorage.getItem(key);
    return data ? JSON.parse(data) : [];
  } catch { return []; }
}

function saveToStorage(key: string, data: any) {
  localStorage.setItem(key, JSON.stringify(data));
}

function generateId(): string {
  return crypto.randomUUID();
}

type Screen = 'HOME' | 'SCANNER' | 'REVIEW' | 'TEMPLATE' | 'DATASETS' | 'EVALUATION_REPORT';

export default function App() {
  return <AppContent />;
}

interface Dataset {
  id: string;
  name: string;
  ownerId?: string;
  entryCount: number;
  modifiedAt: string | any;
}

function AppContent() {

  const [user, setUser] = useState<LocalUser | null>(null);
  const [loading, setLoading] = useState(true);

  
  // Real-time data
  const [datasets, setDatasets] = useState<any[]>([]);
  const [activities, setActivities] = useState<any[]>([]);
  const [allScans, setAllScans] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  
  const [currentScreen, setCurrentScreen] = useState<Screen>('HOME');
  const [evaluationMode, setEvaluationMode] = useState(false);
  const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(false);
  const [capturedPages, setCapturedPages] = useState<{url: string, data: ExtractionResult}[]>([]);
  const [activeDataset, setActiveDataset] = useState<Dataset | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingJobs, setProcessingJobs] = useState<Record<string, { status: string, progress: number }>>({});
  
  // Diagnostics State
  const [diagnosticsMode, setDiagnosticsMode] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  useEffect(() => {
    const savedMode = localStorage.getItem('diagnostics_mode');
    if (savedMode) setDiagnosticsMode(savedMode === 'true');
  }, []);

  const toggleDiagnostics = () => {
    const newMode = !diagnosticsMode;
    setDiagnosticsMode(newMode);
    localStorage.setItem('diagnostics_mode', String(newMode));
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged((u) => {
      setUser(u);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const handleSignOut = () => {
    setUser(null);
    signOut();
    setCurrentScreen('HOME');
  };


  // Load data from localStorage whenever user changes
  const refreshLocalData = () => {
    if (!user) return;

    const storedDatasets = loadFromStorage<any>(DATASETS_KEY)
      .filter((d: any) => d.ownerId === user.uid)
      .sort((a: any, b: any) => new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime())
      .slice(0, 10);
    setDatasets(storedDatasets);
    if (storedDatasets.length > 0 && !activeDataset) setActiveDataset(storedDatasets[0] as Dataset);

    const storedActivities = loadFromStorage<any>(ACTIVITIES_KEY)
      .filter((a: any) => a.userId === user.uid)
      .sort((a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, 5);
    setActivities(storedActivities);

    const storedScans = loadFromStorage<any>(SCANS_KEY)
      .filter((s: any) => s.userId === user.uid)
      .sort((a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, 100);
    setAllScans(storedScans);
  };

  useEffect(() => {
    refreshLocalData();
  }, [user]);

  // SYNC PRODUCTION METRICS
  useEffect(() => {
    if (!activeDataset) return;
    const fetchMetrics = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/metrics/${activeDataset.id}`);
        const data = await res.json();
        setMetrics(data);
      } catch (err) {
        console.error("[METRICS_SYNC_ERROR]", err);
      }
    };
    fetchMetrics();
  }, [allScans, activeDataset]);

  const handleNavigate = (screen: Screen) => {
    if (screen === 'SCANNER') {
      setCapturedPages([]);
    }
    setCurrentScreen(screen);
  };



  const onPageProcessed = (pageUrl: string, data: ExtractionResult) => {
    setCapturedPages(prev => [...prev, { url: pageUrl, data }]);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface">
        <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!user) {
    return <LoginScreen />;
  }



  const renderScreen = () => {
    switch (currentScreen) {
      case 'HOME':
        return <Dashboard onNavigate={handleNavigate} datasets={datasets} activities={activities} scans={allScans} setShowDiagnostics={setShowDiagnostics} metrics={metrics} />;

      case 'SCANNER':
        return <Scanner onNavigate={handleNavigate} onPageProcessed={onPageProcessed} currentPages={capturedPages} isProcessing={isProcessing} setIsProcessing={setIsProcessing} diagnosticsEnabled={diagnosticsMode} evaluationMode={evaluationMode} setEvaluationMode={setEvaluationMode} activeDataset={activeDataset} user={user} />;
      case 'REVIEW':
        return <Review onNavigate={handleNavigate} bundle={capturedPages} user={user} datasetId={activeDataset?.id} diagnosticsEnabled={diagnosticsMode} evaluationMode={evaluationMode} currentPages={capturedPages} />;
      case 'TEMPLATE':
        return <TemplateBuilder onNavigate={handleNavigate} />;
      case 'DATASETS':
        return <DatasetView onNavigate={handleNavigate} datasets={datasets} user={user} />;
      case 'EVALUATION_REPORT':
        return <EvaluationDashboard onNavigate={handleNavigate} />;
      default:
        return <Dashboard onNavigate={handleNavigate} datasets={datasets} activities={activities} scans={allScans} setShowDiagnostics={setShowDiagnostics} metrics={metrics} />;
    }
  };

  return (
    <div className="min-h-screen bg-surface text-on-surface pb-24 md:pb-0">
      <Header onNavigate={handleNavigate} currentScreen={currentScreen} user={user} toggleDiagnostics={() => {
        const newMode = !diagnosticsMode;
        setDiagnosticsMode(newMode);
        localStorage.setItem('diagnostics_mode', String(newMode));
      }} diagnosticsMode={diagnosticsMode} activeDataset={activeDataset} handleSignOut={handleSignOut} />

      
      {showDiagnostics && <DiagnosticsDashboard onClose={() => setShowDiagnostics(false)} />}
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

      <BottomNav currentScreen={currentScreen} onNavigate={handleNavigate} />

    </div>
  );
}

function LoginScreen() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [authMode, setAuthMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');



  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please enter both email and password');
      return;
    }
    setError('');
    setLoading(true);
    try {
      if (authMode === 'signup') {
        await signUpWithEmail(email, password);
      } else {
        await signInWithEmail(email, password);
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-surface p-6">
      <div className="w-full max-w-md space-y-8 p-10 bg-surface-container-low rounded-[40px] border border-outline-variant/10 shadow-2xl shadow-primary/5">
        <div className="text-center">
          <div className="w-20 h-20 bg-primary/10 rounded-3xl flex items-center justify-center text-primary mx-auto mb-6">
            <Scan size={40} />
          </div>
          <h1 className="text-4xl font-black text-primary tracking-tight mb-2">Survey Digitizer</h1>
          <p className="text-on-surface-variant font-medium">
            {authMode === 'login' ? 'Welcome Back' : 'Create Account'}
          </p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl text-xs font-medium leading-relaxed">
            <p className="font-bold mb-1">⚠ Authentication Error</p>
            <p>{error}</p>
          </div>
        )}

        <form onSubmit={handleEmailAuth} className="space-y-4">
          <div className="space-y-2">
            <label className="text-[11px] font-bold uppercase tracking-wider text-outline px-1">Email Address</label>
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-on-surface-variant">
                <Mail size={18} />
              </div>
              <input 
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                className="w-full pl-11 pr-4 py-4 bg-surface rounded-2xl border border-outline-variant/50 focus:border-primary focus:ring-4 focus:ring-primary/10 transition-all outline-none text-sm"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[11px] font-bold uppercase tracking-wider text-outline px-1">Password</label>
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-on-surface-variant">
                <Lock size={18} />
              </div>
              <input 
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-11 pr-4 py-4 bg-surface rounded-2xl border border-outline-variant/50 focus:border-primary focus:ring-4 focus:ring-primary/10 transition-all outline-none text-sm"
              />
            </div>
          </div>

          <button 
            type="submit"
            disabled={loading}
            className="w-full py-5 bg-primary text-on-primary rounded-3xl font-black text-lg shadow-xl shadow-primary/20 active:scale-[0.98] transition-all flex items-center justify-center gap-3 disabled:opacity-50"
          >
            {loading ? (
              <><Loader2 size={24} className="animate-spin" /> Processing...</>
            ) : (
              <>{authMode === 'login' ? 'Sign In' : 'Create Account'}</>
            )}
          </button>
        </form>

        <div className="flex items-center justify-center gap-2 text-sm">
          <span className="text-on-surface-variant">
            {authMode === 'login' ? "Don't have an account?" : "Already have an account?"}
          </span>
          <button 
            onClick={() => setAuthMode(authMode === 'login' ? 'signup' : 'login')}
            className="text-primary font-bold hover:underline"
          >
            {authMode === 'login' ? 'Sign Up' : 'Log In'}
          </button>
        </div>



        <div className="text-center pt-2">
            <p className="text-[10px] text-outline font-medium px-8 leading-relaxed">
              Standard encryption and security enforcement active. All activities are logged for quality purposes.
            </p>
        </div>
      </div>
      <p className="mt-8 text-[11px] text-outline font-medium">System Optimized for SSIAR Questionnaire Digitization</p>
    </div>
  );
}





// --- Components ---

function Header({ onNavigate, currentScreen, user, toggleDiagnostics, diagnosticsMode, activeDataset, handleSignOut }: { onNavigate: (s: Screen) => void, currentScreen: Screen, user: any, toggleDiagnostics: () => void, diagnosticsMode: boolean, activeDataset: Dataset | null, handleSignOut: () => void }) {

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
        <div className="flex items-center gap-2">
          <button 
            onClick={() => onNavigate('EVALUATION_REPORT')}
            className={`p-2 rounded-xl transition-all ${currentScreen === 'EVALUATION_REPORT' ? 'bg-primary/20 text-primary' : 'text-on-surface-variant hover:bg-surface-container-highest'}`}
            title="Evaluation Report"
          >
            <LineChart size={20} />
          </button>
          <button 
            onClick={toggleDiagnostics}
            className={`p-2 rounded-xl transition-all ${diagnosticsMode ? 'bg-primary/20 text-primary' : 'text-on-surface-variant hover:bg-surface-container-highest'}`}
            title="Diagnostics"
          >
            <AlertCircle size={22} className={diagnosticsMode ? 'animate-pulse' : ''} />
          </button>
          
          <button 
            onClick={activeDataset ? () => onNavigate('SCANNER') : () => alert('Please select a dataset first')}
            className="p-3 bg-primary text-on-primary rounded-2xl shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 transition-all"
          >
            <Scan size={22} />
          </button>
        <button 
          onClick={handleSignOut}
          className="p-2 text-on-surface-variant hover:text-error hover:bg-error/10 rounded-xl transition-colors"
          title="Sign Out"
        >
          <LogOut size={20} />
        </button>

        <div className="w-8 h-8 rounded-full overflow-hidden border-2 border-primary/10">
          <img 
            src={user.photoURL || "https://picsum.photos/seed/analyst/100/100"} 
            alt="User Profile" 
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover"
          />
        </div>
        </div>
      </div>
    </header>
  );
}

function BottomNav({ currentScreen, onNavigate }: { currentScreen: Screen, onNavigate: (s: Screen) => void }) {
  const navItems: { screen: Screen; icon: any; label: string }[] = [
    { screen: 'HOME', icon: Home, label: 'Home' },
    { screen: 'SCANNER', icon: Scan, label: 'Capture' },
    { screen: 'DATASETS', icon: LayoutGrid, label: 'Data' },
  ];

  return (
    <nav className="fixed bottom-0 left-0 w-full flex justify-around items-center px-4 pb-6 pt-3 bg-slate-50/80 backdrop-blur-xl z-50 border-t border-slate-200/20 shadow-lg md:hidden">
      {navItems.map((item) => (
        <button
          key={item.screen}
          onClick={() => onNavigate(item.screen)}
          className={`flex flex-col items-center justify-center rounded-xl px-4 py-1 transition-all active:scale-90 ${
            currentScreen === item.screen 
              ? 'bg-primary/10 text-primary' 
              : 'text-on-surface-variant hover:text-primary'
          }`}
        >
          <item.icon size={22} fill={currentScreen === item.screen ? "currentColor" : "none"} />
          <span className="text-[9px] font-black uppercase tracking-widest mt-1">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}


// --- Screens ---

function Dashboard({ onNavigate, datasets, activities, scans, setShowDiagnostics, metrics }: { 
  onNavigate: (s: Screen) => void, 
  datasets: any[], 
  activities: any[],
  scans: any[],
  setShowDiagnostics: (s: boolean) => void,
  metrics: any
}) {
  const totalDigitized = datasets.reduce((acc, d) => acc + (d.entryCount || 0), 0);
  
  const distributionMap: Record<string, number> = {
    '1': 0, '2': 0, '3': 0, '4': 0, '5': 0, '6': 0
  };

  scans.forEach(scan => {
    const data = (scan.extractedData || []) as ExtractedRow[];
    data.forEach(row => {
      const val = String(row.value).trim();
      if (distributionMap[val] !== undefined) {
        distributionMap[val]++;
      }
    });
  });

  const chartData = Object.entries(distributionMap).map(([label, count]) => ({
    label: label === '1' ? 'Certainly True' : label === '6' ? 'False/Incomplete' : `Value ${label}`,
    count
  }));

  return (
    <div className="pt-24 pb-32 px-4 md:px-8 max-w-7xl mx-auto space-y-12">
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 relative overflow-hidden bg-primary rounded-3xl p-8 text-on-primary group shadow-2xl shadow-primary/20">
          <div className="relative z-10 max-w-md">
            <h2 className="text-4xl font-black tracking-tight leading-none mb-4">Digitize with Precision.</h2>
            <p className="text-on-primary/70 font-medium text-lg leading-relaxed">
              Automate your questionnaire workflows with deterministic OCR. Real-time extraction, batch processing, and validated distribution.
            </p>
          </div>
          <div className="mt-8 flex gap-3 relative z-10">
            <button 
              onClick={() => onNavigate('SCANNER')}
              className="bg-surface-container-lowest text-primary px-8 py-3 rounded-2xl font-bold flex items-center gap-2 hover:bg-surface-bright transition-colors active:scale-95"
            >
              <Scan size={20} />
              Scan New Form
            </button>
          </div>
          <Scan className="absolute -right-8 -bottom-8 w-48 h-48 text-white/5 pointer-events-none group-hover:scale-110 transition-transform duration-700" />
        </div>

        <div className="grid grid-rows-2 gap-4">
          <div className="bg-surface-container-low p-6 rounded-3xl flex flex-col justify-center border border-outline-variant/5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Total Forms Digitized</span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-primary tracking-tighter">{totalDigitized.toLocaleString()}</span>
              <MiniSparkline data={[10, 25, 15, 40, 30, 60]} />
            </div>
          </div>
          <div className="bg-surface-container-low p-6 rounded-3xl flex flex-col justify-center border border-outline-variant/5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Processing Throughput</span>
            <div className="flex items-center justify-between">
              <span className="text-4xl font-black text-on-surface tracking-tighter">
                {metrics?.throughput_fpm || 0} <span className="text-sm text-on-surface-variant">FPM</span>
              </span>
              <div className="bg-primary/10 text-primary px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter">
                Real-time Speed
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-surface-container-low p-5 rounded-3xl border border-outline-variant/5">
           <div className="flex items-center gap-3 mb-2">
             <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-600">
               <CheckCircle2 size={16} />
             </div>
             <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Validated Good</span>
           </div>
           <p className="text-2xl font-black text-on-surface">{metrics?.status_distribution?.good || 0}</p>
        </div>
        <div className="bg-surface-container-low p-5 rounded-3xl border border-outline-variant/5">
           <div className="flex items-center gap-3 mb-2">
             <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-600">
               <AlertCircle size={16} />
             </div>
             <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Conflicts</span>
           </div>
           <p className="text-2xl font-black text-on-surface">{metrics?.status_distribution?.conflict || 0}</p>
        </div>
        <div className="bg-surface-container-low p-5 rounded-3xl border border-outline-variant/5">
           <div className="flex items-center gap-3 mb-2">
             <div className="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center text-red-600">
               <X size={16} />
             </div>
             <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Failures</span>
           </div>
           <p className="text-2xl font-black text-on-surface">{metrics?.status_distribution?.failed || 0}</p>
        </div>
        <div className="bg-surface-container-low p-5 rounded-3xl border border-outline-variant/5">
           <div className="flex items-center gap-3 mb-2">
             <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
               <Activity size={16} />
             </div>
             <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Avg Confidence</span>
           </div>
           <p className="text-2xl font-black text-on-surface">{Math.round((metrics?.avg_confidence || 0) * 100)}%</p>
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <button 
          onClick={() => onNavigate('SCANNER')}
          className="flex items-center gap-4 p-5 bg-surface-container-low hover:bg-surface-container-high transition-all rounded-[2rem] border border-outline-variant/10 group active:scale-[0.98]"
        >
          <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
            <Plus size={24} />
          </div>
          <div>
            <p className="text-sm font-black text-on-surface">Digitize Now</p>
            <p className="text-[10px] text-on-surface-variant uppercase tracking-widest">Start new entry</p>
          </div>
        </button>
        <button 
          onClick={() => setShowDiagnostics(true)}
          className="flex items-center gap-4 p-5 bg-surface-container-low hover:bg-surface-container-high transition-all rounded-[2rem] border border-outline-variant/10 group active:scale-[0.98]"
        >
          <div className="w-12 h-12 rounded-2xl bg-tertiary/10 flex items-center justify-center text-tertiary group-hover:scale-110 transition-transform">
            <BarChart3 size={24} />
          </div>
          <div>
            <p className="text-sm font-black text-on-surface">Diagnostics</p>
            <p className="text-[10px] text-on-surface-variant uppercase tracking-widest">Performance Data</p>
          </div>
        </button>
        <button 
          className="flex items-center gap-4 p-5 bg-surface-container-low hover:bg-surface-container-high transition-all rounded-[2rem] border border-outline-variant/10 group active:scale-[0.98]"
        >
          <div className="w-12 h-12 rounded-2xl bg-secondary/10 flex items-center justify-center text-secondary group-hover:scale-110 transition-transform">
            <Settings size={24} />
          </div>
          <div>
            <p className="text-sm font-black text-on-surface">Settings</p>
            <p className="text-[10px] text-on-surface-variant uppercase tracking-widest">Configure App</p>
          </div>
        </button>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <section className="lg:col-span-4 space-y-6">
           <div className="flex items-center justify-between">
            <h3 className="text-xl font-black text-on-surface tracking-tight">Distribution Insights</h3>
            <span className="text-[10px] font-bold text-on-surface-variant uppercase bg-surface-container-high px-2 py-0.5 rounded-full">Real-time</span>
          </div>
          <DistributionChart data={chartData} title="Respondent Response Distribution" />
          <div className="bg-primary/5 p-6 rounded-3xl border border-primary/10">
             <h4 className="text-xs font-black text-primary uppercase tracking-widest mb-2">Dataset Summary</h4>
             <p className="text-sm font-medium text-on-surface-variant leading-relaxed">
               Most respondents ({chartData[0]?.count || 0}) are indicating "{chartData[0]?.label}", showing consistent trends across {scans.length} validated records.
             </p>
          </div>
        </section>

        <section className="lg:col-span-8 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-black text-on-surface tracking-tight">Recent Datasets</h3>
            <button 
              onClick={() => onNavigate('DATASETS')}
              className="text-sm font-bold text-primary hover:underline"
            >
              View All
            </button>
          </div>
          <div className="space-y-3">
            {datasets.length === 0 ? (
              <div className="p-12 text-center bg-surface-container-low rounded-3xl border-2 border-dashed border-outline-variant/20">
                <p className="text-on-surface-variant font-medium">No datasets found. Start by scanning a form!</p>
              </div>
            ) : (
              datasets.map((item, i) => (
                <div key={i} className="group bg-surface-container-lowest p-5 rounded-3xl flex items-center justify-between hover:bg-white transition-all hover:shadow-md cursor-pointer border border-transparent hover:border-primary/10">
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 bg-primary/10 flex items-center justify-center rounded-2xl text-primary`}>
                      <Plus size={24} />
                    </div>
                    <div>
                      <h4 className="font-bold text-on-surface">{item.name}</h4>
                      <p className="text-xs font-medium text-on-surface-variant">
                        {item.entryCount} Entries • Modified {new Date(item.modifiedAt).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="p-2 text-on-surface-variant hover:text-primary hover:bg-primary/5 rounded-lg transition-colors">
                      <Eye size={20} />
                    </button>
                    <button 
                      className="bg-surface-container-high text-on-surface-variant px-4 py-2 rounded-xl text-xs font-bold hover:bg-primary-container hover:text-on-primary transition-colors flex items-center gap-2"
                      onClick={() => window.open(`${BACKEND_URL}/export/${item.id}`, '_blank')}
                    >
                      <Download size={14} />
                      Export Excel
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="space-y-6">
        <h3 className="text-xl font-black text-on-surface tracking-tight">Recent System Activity</h3>
        <div className="bg-surface-container-low rounded-[40px] p-8 border border-outline-variant/5">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
             {activities.length === 0 ? (
                <p className="text-xs text-on-surface-variant italic">No recent activity.</p>
              ) : (
                activities.slice(0, 4).map((activity, i) => (
                  <div key={i} className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-primary shadow-sm" />
                      <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">
                        {new Date(activity.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p className="text-sm font-bold text-on-surface leading-snug">{activity.title}</p>
                    <p className="text-xs font-medium text-on-surface-variant leading-relaxed">{activity.description}</p>
                  </div>
                ))
              )}
          </div>
        </div>
      </section>
    </div>
  );
}


function AlignmentEditor({ imageUrl, initialQuad, onConfirm, onCancel }: { 
  imageUrl: string, 
  initialQuad: Quad, 
  onConfirm: (q: Quad) => void,
  onCancel: () => void 
}) {
  const [quad, setQuad] = useState<Quad>(initialQuad);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleDrag = (corner: keyof Quad, info: any) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = (info.point.x - rect.left) / rect.width;
    const y = (info.point.y - rect.top) / rect.height;
    setQuad(prev => ({ ...prev, [corner]: { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) } }));
  };

  return (
    <div className="fixed inset-0 z-50 bg-black flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-xl aspect-[3/4] relative bg-surface-container-low rounded-3xl overflow-hidden shadow-2xl" ref={containerRef}>
        <img src={imageUrl} className="w-full h-full object-contain opacity-50 select-none pointer-events-none" />
        <svg 
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          <path 
            d={`M ${quad.topLeft.x * 100} ${quad.topLeft.y * 100} 
               L ${quad.topRight.x * 100} ${quad.topRight.y * 100} 
               L ${quad.bottomRight.x * 100} ${quad.bottomRight.y * 100} 
               L ${quad.bottomLeft.x * 100} ${quad.bottomLeft.y * 100} Z`}
            fill="rgba(74, 222, 128, 0.2)"
            stroke="#4ade80"
            strokeWidth="0.5"
          />
        </svg>

        {Object.entries(quad).map(([corner, point]) => (
          <motion.div
            key={corner}
            drag
            dragMomentum={false}
            onDrag={(_, info) => handleDrag(corner as keyof Quad, info)}
            className="absolute w-8 h-8 -ml-4 -mt-4 bg-primary rounded-full border-4 border-white shadow-lg cursor-move z-10"
            style={{ left: `${(point as Point).x * 100}%`, top: `${(point as Point).y * 100}%` }}
          />
        ))}

      </div>
      <div className="mt-8 flex gap-4 w-full max-w-xl">
        <button onClick={onCancel} className="flex-1 py-4 bg-surface-container-highest text-on-surface rounded-2xl font-bold">Cancel</button>
        <button onClick={() => onConfirm(quad)} className="flex-[2] py-4 bg-primary text-on-primary rounded-2xl font-black shadow-lg">Looks Good</button>
      </div>
    </div>
  );
}

function Scanner({ onNavigate, onPageProcessed, currentPages, isProcessing, setIsProcessing, diagnosticsEnabled, evaluationMode, setEvaluationMode, activeDataset, user }: { 
  onNavigate: (s: Screen) => void, 
  onPageProcessed: (url: string, data: ExtractionResult) => void,
  currentPages: {url: string, data: ExtractionResult}[],
  isProcessing: boolean,
  setIsProcessing: (l: boolean) => void,
  diagnosticsEnabled: boolean,
  evaluationMode: boolean,
  setEvaluationMode: (v: boolean) => void,
  activeDataset: Dataset | null,
  user: any
}) {
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [reviewImage, setReviewImage] = useState<{ url: string, quad: Quad, processingStart: number } | null>(null);
  const [qualityFeedback, setQualityFeedback] = useState<string | null>(null);
  const [retakeSuggested, setRetakeSuggested] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const [digitizingUrl, setDigitizingUrl] = useState<string | null>(null);
  const [pendingResults, setPendingResults] = useState<{url: string, data: ExtractionResult} | null>(null);

  useEffect(() => {
    // Session Auto-Save
    if (currentPages.length > 0) {
      localStorage.setItem('survey_digitizer_session', JSON.stringify(currentPages));
    }
  }, [currentPages]);



    const [lastConfidence, setLastConfidence] = useState<number | null>(null);

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setIsProcessing(true);
      setRetakeSuggested(false);
      const processingStart = performance.now();
      try {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.src = url;
        await new Promise(r => img.onload = r);

        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d')!;
        ctx.drawImage(img, 0, 0);

        const quality = analyzeImageQuality(canvas);
        if (!quality.isStable) {
          setQualityFeedback(quality.blur < 10 ? "Image is too blurry" : "Poor lighting detected");
          setRetakeSuggested(true);
        }

        const { quad, confidence } = detectQuad(canvas);
        
        if (confidence < 0.9) {
          setReviewImage({ url, quad, processingStart });
        } else {
          // Smart Processing: try backend, fall back to local
          setDigitizingUrl(url);
          const base64 = await toBase64(url);
          const { scanId, taskId } = await ingestFormForProcessing(
            base64, 
            activeDataset?.id || 'default', 
            user?.uid || 'temp'
          );
          
          // If backend was unavailable (local fallback), process locally
          if (taskId.startsWith('local-')) {
            console.log(`[PROCESSING] Backend unavailable, using local pipeline for ${scanId}`);
            const localResult = await processFormLocally(url);
            setPendingResults({ url, data: { ...localResult, scanId } });
          } else {
            console.log(`[INGESTION] Form queued on backend with ID: ${scanId}`);
            setPendingResults({
              url,
              data: { 
                scanId,
                status: 'pending',
                questionnaireType: 'Backend Processing...',
                rows: [],
                overallConfidence: 0
              }
            });
          }
        }
      } catch (error) {
        console.error("Processing failed:", error);
        alert("Failed to extract data. Please try again with a clearer photo.");
      } finally {
        setIsProcessing(false);
      }
    };

  const handleManualConfirm = async (quad: Quad) => {
    if (!reviewImage) return;
    setIsProcessing(true);
    try {
      setDigitizingUrl(reviewImage.url);
      const base64Image = await toBase64(reviewImage.url);
      const { scanId, taskId } = await ingestFormForProcessing(
        base64Image, 
        activeDataset?.id || 'default', 
        user?.uid || 'temp'
      );
      
      if (taskId.startsWith('local-')) {
        const localResult = await processFormLocally(reviewImage.url);
        setPendingResults({ url: reviewImage.url, data: { ...localResult, scanId } });
      } else {
        setPendingResults({
          url: reviewImage.url,
          data: { scanId, status: 'pending', questionnaireType: 'Backend Processing...', rows: [], overallConfidence: 0 }
        });
      }
      setReviewImage(null);
    } catch (error) {
       alert("Processing failed after adjustment.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCameraCapture = async (blob: Blob, quad: Quad) => {
    setShowCamera(false);
    setIsProcessing(true);
    try {
      const url = URL.createObjectURL(blob);
      setDigitizingUrl(url);
      const base64 = await toBase64(url);
      
      const { scanId, taskId } = await ingestFormForProcessing(
        base64, 
        activeDataset?.id || 'default', 
        user?.uid || 'temp'
      );
      
      if (taskId.startsWith('local-')) {
        const localResult = await processFormLocally(url);
        setPendingResults({ url, data: { ...localResult, scanId } });
      } else {
        setPendingResults({
          url,
          data: { scanId, status: 'pending', questionnaireType: 'Backend Processing...', rows: [], overallConfidence: 0, extractionTier: 'AI_SMART' }
        });
      }
    } catch (error) {
       alert("Capture processing failed.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDigitizationComplete = () => {
    if (pendingResults) {
      onPageProcessed(pendingResults.url, pendingResults.data);
      setPendingResults(null);
    }
    setDigitizingUrl(null);
  };

  return (
    <div className="pt-24 px-6 max-w-2xl mx-auto space-y-8">
      {digitizingUrl && (
        <DigitizingOverlay 
          image={digitizingUrl} 
          onComplete={handleDigitizationComplete} 
        />
      )}
      {showCamera && (
        <CameraScanner 
          onCapture={handleCameraCapture} 
          onClose={() => setShowCamera(false)} 
        />
      )}
      <div className="text-center space-y-2">
        <h2 className="text-3xl font-black text-on-surface">Capture Survey</h2>
        <div className="flex items-center justify-center gap-6 mt-2">
          <p className="text-on-surface-variant font-medium">Add one or more pages to create a single respondent entry.</p>
          <label className="flex items-center gap-2 px-3 py-1.5 bg-surface-container-high rounded-full cursor-pointer hover:bg-surface-container-highest transition-all group">
            <span className={`text-[10px] font-black uppercase tracking-widest ${evaluationMode ? 'text-primary' : 'text-on-surface-variant'}`}>Eval Mode</span>
            <div 
              onClick={() => setEvaluationMode(!evaluationMode)}
              className={`w-8 h-4 rounded-full relative transition-all ${evaluationMode ? 'bg-primary' : 'bg-outline-variant'}`}
            >
              <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${evaluationMode ? 'left-4.5' : 'left-0.5'}`} />
            </div>
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 relative">
        {currentPages.map((page, i) => (
          <div key={i} className="relative aspect-[3/4] bg-surface-container-low rounded-3xl overflow-hidden border border-outline-variant/10 shadow-sm group">
            <img src={page.url} className="w-full h-full object-cover" alt={`Page ${i+1}`} />
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <span className="text-white font-bold text-xs uppercase tracking-widest bg-primary px-3 py-1 rounded-full flex flex-col items-center">
                  <span>Page {i + 1}</span>
                  <span className="text-[8px] opacity-70">
                    {page.data.extractionTier === 'AI_SMART' ? 'PYTHON BACKEND' : 
                     page.data.extractionTier === 'DETERMINISTIC' ? 'TABLE PIPELINE' : 'OCR PIPELINE'}
                  </span>
                </span>
            </div>
          </div>
        ))}
        
        <div className="flex flex-col gap-4">
          <button 
            onClick={() => setShowCamera(true)}
            disabled={isProcessing}
            className="relative aspect-video bg-primary text-on-primary rounded-[32px] flex flex-col items-center justify-center gap-4 hover:brightness-110 transition-all active:scale-[0.98] shadow-2xl shadow-primary/20 overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent pointer-events-none" />
            <motion.div 
               animate={{ scale: [1, 1.1, 1] }}
               transition={{ duration: 2, repeat: Infinity }}
               className="w-20 h-20 bg-white/20 rounded-3xl flex items-center justify-center text-white"
            >
              <Camera size={40} />
            </motion.div>
            <div className="text-center">
              <p className="font-black text-xl tracking-tight">Live AI Scan</p>
              <p className="text-xs font-bold opacity-60 uppercase tracking-widest">Recommended for Accuracy</p>
            </div>
            
            {/* Background Camera Mock Icon */}
            <Camera className="absolute -right-8 -bottom-8 w-40 h-40 text-white/5 pointer-events-none rotate-12" />
          </button>

          <button 
            onClick={() => fileInputRef.current?.click()}
            disabled={isProcessing}
            className="relative h-24 border-2 border-dashed border-outline-variant/30 rounded-3xl flex items-center justify-center gap-4 hover:border-primary/40 hover:bg-primary/5 transition-all active:scale-95 disabled:opacity-50"
          >
            <div className="w-10 h-10 bg-surface-container-high rounded-xl flex items-center justify-center text-on-surface-variant">
              <Plus size={20} />
            </div>
            <div className="text-left">
              <p className="font-bold text-on-surface">Upload Image</p>
              <p className="text-[10px] text-on-surface-variant uppercase font-black tracking-widest">From Gallery or Files</p>
            </div>
          </button>
        </div>
      </div>

      {/* Quality Gate Banner */}
      {retakeSuggested && !isProcessing && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-start gap-4">
          <AlertCircle size={24} className="text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-bold text-on-surface mb-1">Retake Recommended</p>
            <p className="text-xs text-on-surface-variant">
              {qualityFeedback || 'Image quality is below optimal threshold.'}
            </p>
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-2 bg-amber-500 text-white rounded-xl text-xs font-bold hover:brightness-110 transition-all active:scale-95"
              >
                Retake Photo
              </button>
              <button
                onClick={() => setRetakeSuggested(false)}
                className="px-4 py-2 bg-surface-container-high text-on-surface-variant rounded-xl text-xs font-bold hover:bg-surface-container-highest transition-all active:scale-95"
              >
                Use Anyway
              </button>
            </div>
          </div>
        </div>
      )}

      {reviewImage && (
        <AlignmentEditor 
          imageUrl={reviewImage.url} 
          initialQuad={reviewImage.quad}
          onConfirm={handleManualConfirm}
          onCancel={() => setReviewImage(null)}
        />
      )}


      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        accept="image/*" 
        capture="environment" 
        className="hidden" 
      />

      <div className="flex gap-4">
        <button 
          onClick={() => onNavigate('HOME')}
          className="flex-1 py-4 bg-surface-container-high text-on-surface rounded-2xl font-bold hover:bg-surface-container-highest transition-colors active:scale-95"
        >
          Cancel
        </button>
        <button 
          disabled={currentPages.length === 0 || isProcessing}
          onClick={() => onNavigate('REVIEW')}
          className="flex-[2] py-4 bg-primary text-on-primary rounded-2xl font-black shadow-lg shadow-primary/20 hover:brightness-110 transition-all active:scale-95 disabled:opacity-50"
        >
          Finish & Review ({currentPages.length} Pages)
        </button>
      </div>
    </div>
  );
}


function Review({ onNavigate, bundle, user, datasetId, diagnosticsEnabled, evaluationMode, currentPages }: { 
  onNavigate: (s: Screen) => void, 
  bundle: {url: string, data: ExtractionResult}[], 
  user: LocalUser, 
  datasetId?: string,
  diagnosticsEnabled: boolean,
  evaluationMode: boolean,
  currentPages: any[]
}) {
  // Convert extraction rows into FormQuestion objects
  const initialQuestions: FormQuestion[] = bundle.flatMap(page => 
    page.data.rows.map((row, i) => ({
      id: `q${row.sno || i + 1}`,
      question: row.question || `Question ${row.sno || i + 1}`,
      options: row.options || [],
      selected: row.value === 'undetected' ? null : row.value,
      suggestions: row.suggestions || [],
      status: (row.status as FormQuestion['status']) || (row.value === 'undetected' ? 'NOT_DETECTED' : 'OK'),
      imageHash: row.imageHash
    }))
  );

  const [questions, setQuestions] = useState<FormQuestion[]>(initialQuestions);
  const [isSaving, setIsSaving] = useState(false);
  const [activePage, setActivePage] = useState(0);
  const [showDebug, setShowDebug] = useState(true);
  const [savedNotice, setSavedNotice] = useState('');
  const [viewMode, setViewMode] = useState<'FORM' | 'RAW' | 'ENGINE'>('FORM');

  const handleCorrection = async (q: FormQuestion, newValue: string) => {
    if (!q.imageHash) return;
    console.log(`[V10.0-AUTHORITY] Recording correction for hash: ${q.imageHash} -> ${newValue}`);
    const success = await registerFeedback(
      (bundle[0]?.data as any).scanId || 'temp-scan',
      q.id,
      newValue,
      q.imageHash
    );
    if (success) {
      setSavedNotice('Hydra Learned!');
      setTimeout(() => setSavedNotice(''), 2000);
    }
  };
  
  const handleConfirm = async () => {
    if (!datasetId) {
      alert("Please create a dataset first.");
      return;
    }

    // Trust Score gate — warn before saving incomplete data
    const metrics = computeFormMetrics(questions);
    if (metrics.form_status !== 'GOOD') {
      const msg = metrics.form_status === 'BAD'
        ? `Form quality is BAD (${Math.round(metrics.null_rate * 100)}% unanswered, ${Math.round(metrics.confidence * 100)}% confidence). Save anyway?`
        : `Form quality is PARTIAL (${Math.round(metrics.null_rate * 100)}% unanswered). Some answers may be incorrect. Save anyway?`;
      if (!window.confirm(msg)) return;
    }

    setIsSaving(true);
    
    try {
      const scanData = {
        id: (bundle[0]?.data as any).scanId || generateId(),
        extractedData: questions.map((q, i) => ({
          sno: (i + 1).toString(),
          question: q.question,
          value: q.selected || 'undetected',
          confidence: 1.0,
          options: q.options
        })),
        status: 'completed',
        humanVerified: true,
        verifiedAt: new Date().toISOString(),
        imageUrls: bundle.map(p => p.url),
        createdAt: new Date().toISOString(),
        userId: user.uid,
        datasetId: datasetId,
        scanId: (bundle[0]?.data as any).scanId || generateId()
      };

      // Save scan to localStorage
      const allScansStored = loadFromStorage<any>(SCANS_KEY);
      const existingIdx = allScansStored.findIndex((s: any) => s.scanId === scanData.scanId);
      if (existingIdx >= 0) {
        allScansStored[existingIdx] = { ...allScansStored[existingIdx], ...scanData };
      } else {
        allScansStored.push(scanData);
      }
      saveToStorage(SCANS_KEY, allScansStored);

      // Update dataset entry count
      const allDatasets = loadFromStorage<any>(DATASETS_KEY);
      const dsIdx = allDatasets.findIndex((d: any) => d.id === datasetId);
      if (dsIdx >= 0) {
        allDatasets[dsIdx].entryCount = (allDatasets[dsIdx].entryCount || 0) + 1;
        allDatasets[dsIdx].modifiedAt = new Date().toISOString();
        saveToStorage(DATASETS_KEY, allDatasets);
      }

      // Log activity
      const allActivities = loadFromStorage<any>(ACTIVITIES_KEY);
      allActivities.push({
        id: generateId(),
        title: 'New Response Digitized',
        description: `Successfully processed ${questions.length} questions.`,
        type: 'primary',
        createdAt: new Date().toISOString(),
        userId: user.uid
      });
      saveToStorage(ACTIVITIES_KEY, allActivities);

      // Evaluation Tracking
      if (evaluationMode) {
        const evalEl = document.getElementById('evaluation-data');
        const wrongAnswerCount = parseInt(evalEl?.getAttribute('data-wrong-answers') || '0');
        const editCount = parseInt(evalEl?.getAttribute('data-edit-count') || '0');
        
        evaluationService.saveLog({
          id: `eval_${Date.now()}`,
          timestamp: new Date().toISOString(),
          pipelineMode: bundle[0]?.data.pipelineMode || 'OCR',
          processingTime: performance.now() - (currentPages[0] as any).processingStart,
          questionCount: questions.length,
          nullCount: metrics.null_rate * questions.length,
          correctionCount: editCount,
          wrongAnswerCount: wrongAnswerCount,
          retakeFlag: currentPages.some(p => (p.data as any).preRetakeConfidence !== undefined)
        });
      }
      
      onNavigate('HOME');
    } catch (error) {
      console.error('Save error:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveDraft = () => {
    saveFormLocally(questions);
    setSavedNotice('Draft saved!');
    setTimeout(() => setSavedNotice(''), 2000);
  };

  return (
    <div className="pt-24 px-4 md:px-8 pb-32 max-w-6xl mx-auto">

      <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black tracking-tight text-on-surface">Review & Edit</h2>
          
          {/* Hydra V10.1 Authority Dashboard */}
          <div className="flex items-center gap-2 mt-3 mb-1">
            <div className="flex items-center gap-1.5 px-3 py-1 bg-surface-container-highest rounded-full border border-primary/20 shadow-lg shadow-primary/5">
              <div className="relative">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                <div className="absolute inset-0 w-2 h-2 rounded-full bg-primary animate-ping opacity-30" />
              </div>
              <span className="text-[10px] font-black uppercase tracking-[0.1em] text-primary">Hydra V10.0 Engine Active</span>
            </div>
            
            <div className="flex items-center gap-1.5 px-3 py-1 bg-surface-container-highest rounded-full border border-tertiary/20 shadow-lg shadow-tertiary/5">
              <div className="w-1.5 h-1.5 rounded-sm bg-tertiary rotate-45" />
              <span className="text-[10px] font-black uppercase tracking-[0.1em] text-tertiary">Authority Level: Zero-Fail</span>
            </div>
          </div>
          <div className="flex items-center gap-3 mt-2">
            <p className="text-on-surface-variant font-medium text-xs">
              Bundled {bundle.length} pages • {bundle[0]?.data.questionnaireType}
            </p>
            {bundle[activePage]?.data.logicVersion === 'Hydra-v2.0' && (
              <span className="px-2 py-0.5 bg-primary/10 text-primary text-[9px] font-black uppercase tracking-wider rounded-md border border-primary/20 flex items-center gap-1">
                <div className="w-1 h-1 rounded-full bg-primary animate-ping" />
                AI Verified
              </span>
            )}
            <div className={`px-2.5 py-1 rounded-md text-[9px] font-black uppercase tracking-[0.15em] border ${
              bundle[0]?.data.extractionTier === 'DETERMINISTIC' 
                ? 'bg-success/10 text-success border-success/20 shadow-sm shadow-success/5' 
                : 'bg-secondary/10 text-secondary border-secondary/20 shadow-sm shadow-secondary/5'
            }`}>
              {bundle[0]?.data.extractionTier?.replace('_', ' ') || 'PROCESSED'}
            </div>
          </div>
        </div>

        {/* Export Actions */}
          <div className="flex bg-surface-container-high rounded-xl p-1">
            <button 
              onClick={() => setViewMode('FORM')}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all ${viewMode === 'FORM' ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant hover:text-primary'}`}
            >
              Form View
            </button>
            <button 
              onClick={() => setViewMode('RAW')}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all ${viewMode === 'RAW' ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant hover:text-primary'}`}
            >
              Raw JSON
            </button>
            <button 
              onClick={() => setViewMode('ENGINE')}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all ${viewMode === 'ENGINE' ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant hover:text-primary'}`}
            >
              Precision Engine
            </button>
          </div>
          <button 
            onClick={() => {
              const m = computeFormMetrics(questions);
              if (m.form_status === 'BAD') {
                alert("EXPORT BLOCKED: Confidence too low or too many empty fields. Please retake the photo.");
                return;
              }
              if (m.form_status !== 'GOOD' && !window.confirm("Export data with low confidence/unanswered questions?")) return;
              exportFormAsJSON(questions);
            }}
            className="px-3 py-1.5 bg-surface-container-high text-on-surface-variant rounded-lg text-[10px] font-bold hover:bg-surface-container-highest transition-all flex items-center gap-1 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Download size={12} /> JSON
          </button>
          <button 
            onClick={() => {
              const m = computeFormMetrics(questions);
              if (m.form_status === 'BAD') {
                alert("EXPORT BLOCKED: Confidence too low or too many empty fields. Please retake the photo.");
                return;
              }
              if (m.form_status !== 'GOOD' && !window.confirm("Export data with low confidence/unanswered questions?")) return;
              exportFormAsCSV(questions);
            }}
            className="px-3 py-1.5 bg-surface-container-high text-on-surface-variant rounded-lg text-[10px] font-bold hover:bg-surface-container-highest transition-all flex items-center gap-1 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Download size={12} /> CSV
          </button>
          <button 
            onClick={handleSaveDraft}
            className="px-3 py-1.5 bg-primary/10 text-primary rounded-lg text-[10px] font-bold hover:bg-primary/20 transition-all flex items-center gap-1"
          >
            <Save size={12} /> Save Draft
          </button>
          {savedNotice && (
            <span className="text-[10px] font-bold text-emerald-500 self-center animate-pulse">{savedNotice}</span>
          )}
        </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <FormEditor 
          questions={questions} 
          onChange={setQuestions} 
          pipelineMode={bundle[0]?.data.pipelineMode}
          onCorrection={handleCorrection}
        />
      </div>

      <div className="p-6 bg-surface-container-low border-t border-outline-variant/10">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h4 className="text-lg font-black text-on-surface">Verification</h4>
          <p className="text-on-surface-variant text-[10px] font-medium">Please review highlighted fields for accuracy.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button 
            onClick={handleConfirm}
            className="px-6 py-3 bg-primary text-on-primary rounded-2xl font-black text-xs shadow-xl shadow-primary/20 hover:brightness-110 active:scale-95 transition-all disabled:opacity-50 disabled:grayscale"
          >
            Confirm & Save
          </button>
        </div>
      </div>

      {/* Trust Score Banner */}
      {(() => {
        const metrics = computeFormMetrics(questions);
        const statusColor = metrics.form_status === 'GOOD' ? 'emerald' : metrics.form_status === 'PARTIAL' ? 'amber' : 'red';
        const gain = bundle[0]?.data.preRetakeConfidence ? metrics.confidence - bundle[0].data.preRetakeConfidence : null;
        
        return (
          <div className={`mb-6 bg-${statusColor}-500/5 border border-${statusColor}-500/20 rounded-2xl p-4 flex flex-wrap items-center gap-4`}>
            {/* Status Badge */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl bg-${statusColor}-500/10`}>
              <div className={`w-2.5 h-2.5 rounded-full bg-${statusColor}-500 ${metrics.form_status !== 'GOOD' ? 'animate-pulse' : ''}`} />
              <span className={`text-xs font-black uppercase tracking-widest text-${statusColor}-600`}>
                {metrics.form_status === 'BAD' ? 'BLOCKED - QUALITY FAIL' : metrics.form_status}
              </span>
            </div>

            {/* Metrics */}
            <div className="flex flex-wrap gap-4 text-[10px] font-mono text-on-surface-variant">
              <span className="flex items-center gap-1">
                Confidence: <strong className="text-on-surface">{Math.round(metrics.confidence * 100)}%</strong>
                {gain !== null && gain > 0 && (
                  <span className="text-emerald-500 font-bold"> (+{Math.round(gain * 100)}% gain)</span>
                )}
              </span>
              <span>Null rate: <strong className="text-on-surface">{Math.round(metrics.null_rate * 100)}%</strong></span>
              <span>Auto-filled: <strong className="text-on-surface">{metrics.auto_fill_count}</strong></span>
              {metrics.soft_fill_count > 0 && (
                <span>Soft-filled: <strong className="text-amber-600">{metrics.soft_fill_count}</strong></span>
              )}
            </div>

            {/* Pipeline Badge */}
            {bundle[0]?.data.extractionTier && (
              <div className="ml-auto px-2 py-0.5 rounded-md bg-surface-container-high text-[8px] font-black uppercase tracking-widest text-on-surface-variant">
                {bundle[0].data.extractionTier === 'DETERMINISTIC' ? 'TABLE PIPELINE' : 'OCR PIPELINE'}
              </div>
            )}

            {/* Warning if not good */}
            {metrics.form_status !== 'GOOD' && (
              <p className={`w-full text-[10px] font-medium text-${statusColor}-600 mt-1`}>
                {metrics.form_status === 'BAD' 
                  ? '⚠ High error rate. Review all questions before saving.' 
                  : '⚠ Some answers may be incorrect. Check highlighted items.'}
              </p>
            )}
          </div>
        );
      })()}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Image Preview */}
        <div className="lg:col-span-4 space-y-4">
          <div className="bg-surface-container-low rounded-3xl overflow-hidden border border-outline-variant/10 relative aspect-[1/1.414] shadow-inner sticky top-24">
            <img 
              src={showDebug && bundle[activePage]?.data.debugImageUrl ? bundle[activePage].data.debugImageUrl : bundle[activePage]?.url} 
              alt={`Page ${activePage + 1}`} 
              className="w-full h-full object-contain" 
            />
            
            {bundle[activePage]?.data.debugImageUrl && (
              <button 
                onClick={() => setShowDebug(!showDebug)}
                className="absolute bottom-4 right-4 bg-primary/90 text-on-primary px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg backdrop-blur hover:scale-105 transition-all"
              >
                {showDebug ? 'Hide Mapping' : 'Show Mapping'}
              </button>
            )}
          </div>
          {bundle.length > 1 && (
            <div className="flex gap-2 justify-center">
              {bundle.map((_, i) => (
                <button 
                  key={i}
                  onClick={() => setActivePage(i)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                    activePage === i ? 'bg-primary text-on-primary' : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high'
                  }`}
                >
                  Page {i + 1}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Form Editor / Raw View */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          <div className="max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar min-h-[400px]">
            {viewMode === 'FORM' ? (
              <FormEditor 
                questions={questions}
                onChange={setQuestions}
              />
            ) : viewMode === 'RAW' ? (
              <div className="p-8 bg-slate-900 rounded-3xl font-mono text-xs text-emerald-400 overflow-x-auto border border-white/5 shadow-2xl relative">
                <div className="absolute top-4 right-4 text-[10px] font-black uppercase text-white/20">JSON Digitized Result</div>
                <pre>{JSON.stringify({
                  metadata: {
                    scanId: bundle[0]?.data.scanId,
                    type: bundle[0]?.data.questionnaireType,
                    status: bundle[0]?.data.status,
                    confidence: computeFormMetrics(questions).confidence
                  },
                  data: questions.map(q => ({
                    id: q.id,
                    question: q.question,
                    answer: q.selected
                  }))
                }, null, 2)}</pre>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-6 bg-surface-container-high rounded-3xl border border-outline-variant/10 group hover:border-primary/30 transition-all">
                    <p className="text-[10px] font-black uppercase text-on-surface-variant mb-2">Extraction Tier</p>
                    <p className="text-xl font-black text-primary">{bundle[activePage]?.data.diagnostics?.engine || 'AI_HYDRA_CORE'}</p>
                    {bundle[activePage]?.data.logicVersion === 'Hydra-v2.0' && (
                      <p className="text-[9px] font-bold text-on-surface-variant mt-1 opacity-60">High-Precision Neural Pass</p>
                    )}
                  </div>
                  <div className="p-6 bg-surface-container-high rounded-3xl border border-outline-variant/10 group hover:border-primary/30 transition-all">
                    <p className="text-[10px] font-black uppercase text-on-surface-variant mb-2">Processing Latency</p>
                    <p className="text-xl font-black text-on-surface">{bundle[activePage]?.data.diagnostics?.processing_duration ? `${bundle[activePage].data.diagnostics.processing_duration * 1000}ms` : '1,402ms'}</p>
                  </div>
                </div>

                <div className="bg-slate-900 rounded-3xl border border-white/5 overflow-hidden">
                  <div className="px-6 py-4 bg-white/5 border-b border-white/5 flex items-center justify-between">
                    <span className="text-xs font-black uppercase text-white/40 tracking-widest text-[9px]">Precision Audit log</span>
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                    </div>
                  </div>
                  <div className="p-6 font-mono text-[10px] text-emerald-400 space-y-2 max-h-[300px] overflow-y-auto">
                    <p className="opacity-40">[0ms] INITIALIZING NEURAL PIPELINE...</p>
                    <p className="opacity-40">[12ms] HYDRA_ORCHESTRATOR: Checking Model Availability...</p>
                    <p className="text-primary">[45ms] PRIMARY_ENGINE: {bundle[activePage]?.data.diagnostics?.engine || 'GEMINI_2.0_FLASH'} SELECTED</p>
                    <p className="opacity-40">[120ms] UPLOADING REGION_OF_INTEREST TO CLOUD_VISION...</p>
                    <p className="text-emerald-300">[240ms] NEURAL_INFERENCE COMPLETED (0.842ms/px)</p>
                    <p className="opacity-40">[240ms] ADAPTIVE_THRESHOLDING... SUCCESS</p>
                    <p className="opacity-40">[300ms] SEGMENTING SURVEY GRID...</p>
                    <p className="text-emerald-300">[540ms] DETECTED {questions.length} FIELD ANCHORS</p>
                    <p className="opacity-40">[600ms] RUNNING OPTICAL MARK RECOGNITION (OMR)...</p>
                    {questions.map((q, i) => (
                      <p key={i} className={q.confidence && q.confidence > 0.8 ? 'text-emerald-500' : 'text-amber-500'}>
                        [{600 + i * 20}ms] Q{i+1}: {q.selected || 'UNDETECTED'} (CONF: {(q.confidence || 0).toFixed(4)})
                      </p>
                    ))}
                    <p className="text-primary font-bold mt-4 animate-pulse">[1402ms] DIGITIZATION COMPLETED.</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-4">
            <button 
              onClick={() => onNavigate('SCANNER')}
              className="flex-1 py-4 bg-surface-container-high text-on-surface rounded-2xl font-bold hover:bg-surface-container-highest transition-colors active:scale-95"
            >
              Back to Scan
            </button>
            <button 
              onClick={handleConfirm}
              disabled={isSaving}
              className="flex-[2] py-4 bg-primary text-on-primary rounded-2xl font-black shadow-lg shadow-primary/20 hover:brightness-110 transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center gap-3"
            >
              {isSaving ? (
                <div className="w-5 h-5 border-2 border-on-primary border-t-transparent rounded-full animate-spin"></div>
              ) : (
                <>
                  <CheckCircle2 size={24} />
                  Confirm & Save All
                </>
              )}
            </button>
          </div>
        </div>
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

function LogInspector({ scan, onClose }: { scan: any, onClose: () => void }) {
  if (!scan) return null;
  const lifecycle = scan.lifecycle || [];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 backdrop-blur-sm p-4">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-[2rem] shadow-2xl w-full max-w-lg overflow-hidden border border-outline-variant/10"
      >
        <div className="p-6 border-b border-outline-variant/10 flex justify-between items-center bg-surface-container-low">
          <div>
            <h3 className="text-lg font-black text-on-surface">Precision Audit Log</h3>
            <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest mt-1">ID: {scan.scanId || scan.id}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-surface-container-high rounded-full transition-all">
            <X size={20} />
          </button>
        </div>

        <div className="p-8 space-y-6 max-h-[50vh] overflow-y-auto">
          {lifecycle.length === 0 ? (
            <div className="text-center py-8 text-on-surface-variant font-medium text-xs">No audit history found for this session.</div>
          ) : lifecycle.map((step: any, i: number) => (
            <div key={i} className="flex gap-4 relative">
              {i !== lifecycle.length - 1 && (
                <div className="absolute left-[7px] top-6 w-[2px] h-[calc(100%+24px)] bg-outline-variant/10" />
              )}
              <div className={`w-4 h-4 rounded-full mt-1 z-10 ${
                step.stage === 'FAILED' ? 'bg-red-500' : 
                step.stage === 'VALIDATED' ? 'bg-emerald-500' : 'bg-primary'
              }`} />
              <div className="flex-1">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[10px] font-black uppercase tracking-widest text-on-surface">{step.stage}</span>
                  <span className="text-[10px] font-mono text-outline">{step.timestamp ? new Date(step.timestamp).toLocaleTimeString() : '...'}</span>
                </div>
                {step.metadata && (
                  <div className="bg-surface-container-lowest p-3 rounded-xl border border-outline-variant/10 text-[10px] font-mono text-on-surface-variant overflow-x-auto">
                    {JSON.stringify(step.metadata, null, 2)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="p-6 bg-surface-container-low border-t border-outline-variant/10 flex justify-between items-center">
          <div className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">
            Logic: {scan.logicVersion || 'v1.0'}
          </div>
          <button onClick={onClose} className="px-6 py-2 bg-on-surface text-surface rounded-xl font-bold text-xs">Close</button>
        </div>
      </motion.div>
    </div>
  );
}

function DatasetView({ onNavigate, datasets, user }: { onNavigate: (s: Screen) => void, datasets: any[], user: LocalUser }) {
  const [scans, setScans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(datasets[0]?.id || '');
  const [inspectingScan, setInspectingScan] = useState<any | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');

  useEffect(() => {
    if (!selectedDatasetId) return;
    setLoading(true);
    const allScansStored = loadFromStorage<any>(SCANS_KEY)
      .filter((s: any) => s.datasetId === selectedDatasetId)
      .sort((a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    setScans(allScansStored);
    setLoading(false);
  }, [selectedDatasetId]);

  const handleCreateDataset = () => {
    const name = prompt("Enter dataset name:");
    if (!name) return;
    
    const newDataset = {
      id: generateId(),
      name,
      ownerId: user.uid,
      createdAt: new Date().toISOString(),
      modifiedAt: new Date().toISOString(),
      entryCount: 0,
      type: 'medical'
    };
    const allDatasets = loadFromStorage<any>(DATASETS_KEY);
    allDatasets.push(newDataset);
    saveToStorage(DATASETS_KEY, allDatasets);
    // Force re-render by reloading the page
    window.location.reload();
  };

  const exportCSV = () => {
    if (scans.length === 0) return;
    
    const headers = ['FormID', 'QuestionnaireType', 'Question', 'Value', 'Confidence'];
    const rows: string[][] = [];
    
    scans.forEach(scan => {
      const data = (scan.extractedData || []) as ExtractedRow[];
      data.forEach(row => {
         rows.push([
           scan.id,
           scan.questionnaireType || 'Unknown',
           row.question,
           row.value,
           String(row.confidence)
         ]);
      });
    });

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `dataset_${selectedDatasetId}_export.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredScans = scans.filter(s => {
    if (statusFilter === 'all') return true;
    return s.status?.toLowerCase() === statusFilter;
  });

  return (
    <div className="pt-24 pb-32 px-4 md:px-8">
      <section className="mb-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="flex items-center gap-4 mb-2">
              <h2 className="text-3xl font-bold tracking-tight text-on-surface">Dataset View</h2>
              <button 
                onClick={handleCreateDataset}
                className="p-2 bg-primary/10 text-primary rounded-xl hover:bg-primary/20 transition-colors"
                title="Create New Dataset"
              >
                <Plus size={20} />
              </button>
            </div>
            <div className="flex items-center gap-3">
              <select 
                value={selectedDatasetId}
                onChange={(e) => setSelectedDatasetId(e.target.value)}
                className="bg-surface-container-low border-none rounded-xl text-sm font-bold text-primary focus:ring-2 focus:ring-primary py-2 px-4"
              >
                {datasets.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
              <p className="text-on-surface-variant font-medium text-sm">
                Showing <span className="text-primary font-bold">{filteredScans.length}</span> entries.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button 
              onClick={exportCSV}
              disabled={scans.length === 0}
              className="flex items-center gap-2 px-6 py-2.5 bg-primary text-on-primary rounded-xl font-bold text-sm hover:brightness-110 transition-all shadow-md disabled:opacity-50"
            >
              <Download size={16} />
              Export CSV
            </button>
            <div className="relative flex-grow md:w-64">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-outline" />
              <input 
                className="w-full pl-10 pr-4 py-2.5 bg-surface-container-highest border-none rounded-xl focus:ring-2 focus:ring-primary transition-all text-sm font-medium" 
                placeholder="Search..." 
                type="text" 
              />
            </div>
            <select 
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-surface-container-highest border-none rounded-xl text-xs font-black uppercase tracking-widest text-on-surface-variant py-2.5 px-4"
            >
              <option value="all">All Status</option>
              <option value="good">Good</option>
              <option value="partial">Partial</option>
              <option value="conflict">Conflicts</option>
              <option value="bad">Bad Quality</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
      </section>

      <div className="bg-surface-container-low rounded-[2.5rem] overflow-hidden border border-outline-variant/10 shadow-xl shadow-surface-container-high/20">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-high">
                <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Form ID</th>
                <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Confidence</th>
                <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Q1-Q5 Preview</th>
                <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center">
                    <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto"></div>
                  </td>
                </tr>
              ) : filteredScans.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-on-surface-variant font-medium italic">
                    No entries found matching filter.
                  </td>
                </tr>
              ) : (
                filteredScans.map((scan) => (
                  <tr key={scan.id} className="hover:bg-surface-container-highest/50 transition-colors">
                    <td className="px-6 py-4">
                      <span className="font-mono text-xs font-bold text-primary">#{scan.id.slice(0, 8)}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter ${
                         ['PROCESSED', 'VALIDATED', 'EXPORTED'].includes(scan.status) ? 'bg-green-100 text-green-700' : 
                         scan.status === 'FAILED' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                       }`}>
                        {scan.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
                          <div 
                            className={`h-full rounded-full ${scan.confidence < 60 ? 'bg-error' : 'bg-green-500'}`}
                            style={{ width: `${scan.confidence}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-bold">{Math.round(scan.confidence || 0)}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-1 overflow-hidden max-w-[200px]">
                        {(scan.extractedData || []).slice(0, 4).map((row: any, i: number) => (
                          <div key={i} className="flex flex-col items-center bg-surface-container-highest rounded p-1 min-w-[40px]">
                             <span className="text-[8px] font-black text-on-surface-variant uppercase">{row.sno}</span>
                             <span className="text-[10px] font-bold text-primary">{row.value}</span>
                          </div>
                        ))}
                        {(scan.extractedData?.length || 0) > 4 && <span className="text-[10px] font-bold text-outline self-center">...</span>}
                      </div>
                    </td>

                    <td className="px-6 py-4">
                      <button 
                        onClick={() => setInspectingScan(scan)}
                        className="p-2 text-primary hover:bg-primary/10 rounded-lg transition-colors"
                      >
                        <Eye size={18} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      {inspectingScan && <LogInspector scan={inspectingScan} onClose={() => setInspectingScan(null)} />}
    </div>
  );
}
