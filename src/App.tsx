/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, Component } from 'react';
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
  LogIn
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  onAuthStateChanged, 
  User 
} from 'firebase/auth';
import { 
  collection, 
  onSnapshot, 
  query, 
  orderBy, 
  limit, 
  addDoc, 
  serverTimestamp,
  doc,
  updateDoc,
  deleteDoc,
  getDocs,
  getDocFromServer,
  where,
  increment
} from 'firebase/firestore';
import { auth, db, signIn, signOut } from './lib/firebase';
import { processFormImage } from './services/processingService';
import { standardSurveyTemplate } from './services/templateService';

enum OperationType {
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  LIST = 'list',
  GET = 'get',
  WRITE = 'write',
}

interface FirestoreErrorInfo {
  error: string;
  operationType: OperationType;
  path: string | null;
  authInfo: {
    userId: string | undefined;
    email: string | null | undefined;
    emailVerified: boolean | undefined;
    isAnonymous: boolean | undefined;
    tenantId: string | null | undefined;
    providerInfo: {
      providerId: string;
      displayName: string | null;
      email: string | null;
      photoUrl: string | null;
    }[];
  }
}

function handleFirestoreError(error: unknown, operationType: OperationType, path: string | null) {
  const errInfo: FirestoreErrorInfo = {
    error: error instanceof Error ? error.message : String(error),
    authInfo: {
      userId: auth.currentUser?.uid,
      email: auth.currentUser?.email,
      emailVerified: auth.currentUser?.emailVerified,
      isAnonymous: auth.currentUser?.isAnonymous,
      tenantId: auth.currentUser?.tenantId,
      providerInfo: auth.currentUser?.providerData.map(provider => ({
        providerId: provider.providerId,
        displayName: provider.displayName,
        email: provider.email,
        photoUrl: provider.photoURL
      })) || []
    },
    operationType,
    path
  }
  console.error('Firestore Error: ', JSON.stringify(errInfo));
  // Removed throw to avoid breaking the app if not caught
}

type Screen = 'HOME' | 'SCAN' | 'REVIEW' | 'TEMPLATE' | 'DATASET';

export default function App() {
  return <AppContent />;
}

function AppContent() {
  const [currentScreen, setCurrentScreen] = useState<Screen>('HOME');
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Real-time data
  const [datasets, setDatasets] = useState<any[]>([]);
  const [activities, setActivities] = useState<any[]>([]);
  const [scans, setScans] = useState<any[]>([]);
  const [currentScan, setCurrentScan] = useState<any>(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });

    async function testConnection() {
      try {
        await getDocFromServer(doc(db, 'test', 'connection'));
      } catch (error) {
        if(error instanceof Error && error.message.includes('the client is offline')) {
          console.error("Please check your Firebase configuration. ");
        }
      }
    }
    testConnection();

    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!user) return;

    // Listen to datasets
    const datasetsPath = 'datasets';
    const datasetsQuery = query(
      collection(db, datasetsPath), 
      where('ownerId', '==', user.uid),
      orderBy('modifiedAt', 'desc'), 
      limit(10)
    );
    const unsubDatasets = onSnapshot(datasetsQuery, (snapshot) => {
      setDatasets(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    }, (error) => {
      handleFirestoreError(error, OperationType.LIST, datasetsPath);
    });

    // Listen to activities
    const activitiesPath = 'activities';
    const activitiesQuery = query(
      collection(db, activitiesPath), 
      where('userId', '==', user.uid), // Added userId filter
      orderBy('createdAt', 'desc'), 
      limit(5)
    );
    const unsubActivities = onSnapshot(activitiesQuery, (snapshot) => {
      setActivities(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    }, (error) => {
      handleFirestoreError(error, OperationType.LIST, activitiesPath);
    });

    return () => {
      unsubDatasets();
      unsubActivities();
    };
  }, [user]);

  const handleScan = async () => {
    if (!user) return;
    setCurrentScreen('SCAN');
  };

  const onScanComplete = async (scanData: any) => {
    const newScan = {
      ...scanData,
      status: scanData.confidence < 60 ? 'conflict' : 'pending',
      createdAt: serverTimestamp(),
      userId: user?.uid,
      datasetId: datasets[0]?.id || 'default_dataset' // Ensure datasetId is present
    };
    
    const datasetId = newScan.datasetId;
    const scansPath = `datasets/${datasetId}/scans`;
    
    try {
      const docRef = await addDoc(collection(db, scansPath), newScan);
      setCurrentScan({ id: docRef.id, ...newScan });
      setCurrentScreen('REVIEW');
      
      // Log activity
      await addDoc(collection(db, 'activities'), {
        title: 'New Scan Processed',
        description: `Scan #${docRef.id.slice(0, 5)} added to dataset.`,
        type: 'primary',
        createdAt: serverTimestamp(),
        userId: user?.uid // Added userId
      });
    } catch (error) {
      handleFirestoreError(error, OperationType.CREATE, scansPath);
    }
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
        return <Dashboard onNavigate={setCurrentScreen} datasets={datasets} activities={activities} />;
      case 'SCAN':
        return <Scanner onNavigate={setCurrentScreen} onComplete={onScanComplete} />;
      case 'REVIEW':
        return <Review onNavigate={setCurrentScreen} scan={currentScan} />;
      case 'TEMPLATE':
        return <TemplateBuilder onNavigate={setCurrentScreen} />;
      case 'DATASET':
        return <DatasetView onNavigate={setCurrentScreen} datasets={datasets} user={user} />;
      default:
        return <Dashboard onNavigate={setCurrentScreen} datasets={datasets} activities={activities} />;
    }
  };

  return (
    <div className="min-h-screen bg-surface text-on-surface pb-24 md:pb-0">
      <Header onNavigate={setCurrentScreen} currentScreen={currentScreen} user={user} />
      
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

function LoginScreen() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-surface p-6 text-center">
      <div className="w-20 h-20 bg-primary/10 rounded-3xl flex items-center justify-center text-primary mb-8">
        <Scan size={40} />
      </div>
      <h1 className="text-4xl font-black text-primary tracking-tight mb-4">Survey Digitizer</h1>
      <p className="text-on-surface-variant max-w-xs mb-12 font-medium">
        Convert your physical survey data into digital insights in seconds.
      </p>
      <button 
        onClick={signIn}
        className="flex items-center gap-3 bg-primary text-on-primary px-8 py-4 rounded-2xl font-bold shadow-lg active:scale-95 transition-all"
      >
        <LogIn size={20} />
        Sign in with Google
      </button>
    </div>
  );
}

// --- Components ---

function Header({ onNavigate, currentScreen, user }: { onNavigate: (s: Screen) => void, currentScreen: Screen, user: User }) {
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
        <button 
          onClick={signOut}
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

function Dashboard({ onNavigate, datasets, activities }: { onNavigate: (s: Screen) => void, datasets: any[], activities: any[] }) {
  const totalDigitized = datasets.reduce((acc, d) => acc + (d.entryCount || 0), 0);
  
  return (
    <div className="pt-24 px-6 space-y-8 pb-12">
      {/* Hero Section */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 bg-gradient-to-br from-primary to-primary-container p-8 rounded-3xl flex flex-col justify-between min-h-[240px] relative overflow-hidden group shadow-lg">
          <div className="relative z-10">
            <h2 className="text-on-primary text-3xl font-bold tracking-tight mb-2">Digitize New Dataset</h2>
            <p className="text-on-primary/80 max-w-md font-medium">
              Upload paper surveys or capture images to convert physical data into structured CSV/Excel formats using our OCR engine.
            </p>
          </div>
          <div className="mt-8 flex gap-3 relative z-10">
            <button 
              onClick={() => onNavigate('SCAN')}
              className="bg-surface-container-lowest text-primary px-8 py-3 rounded-2xl font-bold flex items-center gap-2 hover:bg-surface-bright transition-colors active:scale-95"
            >
              <Scan size={20} />
              Scan New Form
            </button>
            <button className="bg-primary-container/30 text-on-primary border border-on-primary/20 backdrop-blur-md px-6 py-3 rounded-2xl font-bold hover:bg-primary-container/50 transition-colors">
              Bulk Upload
            </button>
          </div>
          <Scan className="absolute -right-8 -bottom-8 w-48 h-48 text-white/5 pointer-events-none group-hover:scale-110 transition-transform duration-700" />
        </div>

        {/* Stats */}
        <div className="grid grid-rows-2 gap-4">
          <div className="bg-surface-container-low p-6 rounded-3xl flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Total Forms Digitized</span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-primary tracking-tighter">{totalDigitized.toLocaleString()}</span>
              <span className="text-xs font-bold text-tertiary">+12% this month</span>
            </div>
          </div>
          <div className="bg-surface-container-low p-6 rounded-3xl flex flex-col justify-center">
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
                        {item.entryCount} Entries • Modified {new Date(item.modifiedAt?.seconds * 1000).toLocaleDateString()}
                      </p>
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
              ))
            )}
          </div>
        </section>

        {/* Recent Projects / Activity */}
        <section className="lg:col-span-4 space-y-6">
          <h3 className="text-xl font-black text-on-surface tracking-tight">Recent Projects</h3>
          <div className="bg-surface-container-low rounded-3xl p-6 space-y-6">
            <div className="relative pl-6 border-l-2 border-primary/20 space-y-8">
              {activities.length === 0 ? (
                <p className="text-xs text-on-surface-variant italic">No recent activity.</p>
              ) : (
                activities.map((activity, i) => (
                  <div key={i} className="relative">
                    <div className={`absolute -left-[31px] top-0 w-4 h-4 rounded-full bg-primary ring-4 ring-surface-container-low`}></div>
                    <div className="space-y-1">
                      <p className="text-sm font-bold text-on-surface">{activity.title}</p>
                      <p className="text-xs text-on-surface-variant">{activity.description}</p>
                      <p className="text-[10px] font-bold text-primary-container uppercase mt-2">
                        {new Date(activity.createdAt?.seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
            <button className="w-full py-3 bg-surface-container-high rounded-2xl text-xs font-bold text-primary hover:bg-primary/5 transition-colors">
              View Full Audit Log
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

function Scanner({ onNavigate, onComplete }: { onNavigate: (s: Screen) => void, onComplete: (data: any) => void }) {
  const [isScanning, setIsScanning] = useState(false);
  const [capturedPages, setCapturedPages] = useState<string[]>([]);
  const [mode, setMode] = useState<'single' | 'multi'>('single');

  const handleCapture = async () => {
    // In a real app, we'd capture from camera. For demo, we use a placeholder.
    const mockImageUrl = `https://picsum.photos/seed/form-${capturedPages.length}/1000/1414`;
    
    if (mode === 'multi') {
      setCapturedPages([...capturedPages, mockImageUrl]);
    } else {
      processImage(mockImageUrl);
    }
  };

  const processImage = async (url: string) => {
    setIsScanning(true);
    try {
      const result = await processFormImage(url, standardSurveyTemplate, 1);
      onComplete({
        extractedData: result.answers,
        fieldsConfidence: result.confidences,
        confidence: Object.values(result.confidences).reduce((a, b) => a + b, 0) / Object.keys(result.confidences).length,
        alignedImageUrl: result.alignedImageUrl,
        pages: [url]
      });
    } catch (error) {
      console.error("Processing failed:", error);
      setIsScanning(false);
    }
  };

  const handleFinishMulti = async () => {
    if (capturedPages.length === 0) return;
    setIsScanning(true);
    try {
      // Combine multiple pages. For now, we just process the first page as a demo
      // but the structure supports combining results.
      const result = await processFormImage(capturedPages[0], standardSurveyTemplate, 1);
      onComplete({
        extractedData: result.answers,
        fieldsConfidence: result.confidences,
        confidence: Object.values(result.confidences).reduce((a, b) => a + b, 0) / Object.keys(result.confidences).length,
        alignedImageUrl: result.alignedImageUrl,
        pages: capturedPages
      });
    } catch (error) {
      console.error("Multi-page processing failed:", error);
      setIsScanning(false);
    }
  };

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
          <span className="text-[10px] font-bold uppercase tracking-widest text-white">
            {isScanning ? 'Processing...' : 'Live Engine Active'}
          </span>
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
          <div className="absolute inset-0 border-2 border-dashed border-white/40 rounded-3xl flex items-center justify-center">
            {isScanning ? (
              <div className="flex flex-col items-center gap-4">
                <div className="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                <p className="text-white font-bold text-sm uppercase tracking-widest">Analyzing Template...</p>
              </div>
            ) : (
              <div className="text-white/80 bg-black/40 backdrop-blur-sm px-6 py-2 rounded-full font-bold text-xs uppercase tracking-tighter">
                Align form with markers
              </div>
            )}
          </div>
          {/* Corner Brackets */}
          <div className="absolute -top-2 -left-2 w-12 h-12 border-t-4 border-l-4 border-primary rounded-tl-3xl shadow-lg"></div>
          <div className="absolute -top-2 -right-2 w-12 h-12 border-t-4 border-r-4 border-primary rounded-tr-3xl shadow-lg"></div>
          <div className="absolute -bottom-2 -left-2 w-12 h-12 border-b-4 border-l-4 border-primary rounded-bl-3xl shadow-lg"></div>
          <div className="absolute -bottom-2 -right-2 w-12 h-12 border-b-4 border-r-4 border-primary rounded-br-3xl shadow-lg"></div>
        </div>

        {/* Status Indicators */}
        <div className="absolute top-24 left-0 w-full flex justify-center gap-3 z-20">
          <div className="flex items-center gap-2 bg-black/60 backdrop-blur-xl border border-white/10 px-4 py-2 rounded-2xl">
            <Sun size={14} className="text-green-400" />
            <span className="text-xs font-bold text-white tracking-tight">Lighting: Good</span>
          </div>
          <div className="flex items-center gap-2 bg-black/60 backdrop-blur-xl border border-white/10 px-4 py-2 rounded-2xl">
            <Maximize size={14} className="text-blue-400" />
            <span className="text-xs font-bold text-white tracking-tight">Alignment: OK</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="relative z-50 px-8 pb-10 pt-12 bg-gradient-to-t from-black via-black/80 to-transparent">
        <div className="max-w-md mx-auto flex items-center justify-between">
          <div className="relative cursor-pointer group">
            <div className="w-14 h-14 rounded-2xl overflow-hidden border-2 border-white/20 group-hover:border-primary transition-all">
              {capturedPages.length > 0 ? (
                <img src={capturedPages[capturedPages.length - 1]} alt="Last capture" referrerPolicy="no-referrer" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full bg-white/10 flex items-center justify-center text-white/40">
                  <Plus size={20} />
                </div>
              )}
            </div>
            {capturedPages.length > 0 && (
              <span className="absolute -top-2 -right-2 bg-primary text-white text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center">
                {capturedPages.length}
              </span>
            )}
          </div>

          <button 
            onClick={handleCapture}
            disabled={isScanning}
            className="relative w-20 h-20 rounded-full bg-white flex items-center justify-center shadow-2xl active:scale-90 transition-transform disabled:opacity-50 disabled:scale-95"
          >
            <div className="w-[72px] h-[72px] rounded-full border-2 border-black/5"></div>
          </button>

          {mode === 'multi' ? (
            <button 
              onClick={handleFinishMulti}
              disabled={capturedPages.length === 0 || isScanning}
              className="w-14 h-14 flex items-center justify-center rounded-full bg-primary text-white active:scale-95 transition-all disabled:opacity-50"
            >
              <CheckCircle2 size={24} />
            </button>
          ) : (
            <button className="w-14 h-14 flex items-center justify-center rounded-full bg-white/10 backdrop-blur-md text-white active:bg-white active:text-black transition-all">
              <Flashlight size={24} />
            </button>
          )}
        </div>

        <div className="mt-8 flex justify-center gap-8">
          <button 
            onClick={() => setMode('single')}
            className={`text-xs font-black uppercase tracking-[0.2em] transition-colors ${mode === 'single' ? 'text-white' : 'text-white/40'}`}
          >
            Single Page
          </button>
          <button 
            onClick={() => setMode('multi')}
            className={`text-xs font-black uppercase tracking-[0.2em] transition-colors ${mode === 'multi' ? 'text-white' : 'text-white/40'}`}
          >
            Multi-page
          </button>
        </div>
      </footer>
    </div>
  );
}

function Review({ onNavigate, scan }: { onNavigate: (s: Screen) => void, scan: any }) {
  const [editedData, setEditedData] = useState(scan?.extractedData || {});
  const [isSaving, setIsSaving] = useState(false);
  const [activeQuestion, setActiveQuestion] = useState(0);

  if (!scan) {
    return (
      <div className="pt-24 px-6 text-center">
        <p className="text-on-surface-variant">No scan selected for review.</p>
        <button onClick={() => onNavigate('HOME')} className="mt-4 text-primary font-bold">Go Home</button>
      </div>
    );
  }

  const handleConfirm = async () => {
    setIsSaving(true);
    const datasetId = scan.datasetId || 'default_dataset';
    const scanPath = `datasets/${datasetId}/scans/${scan.id}`;
    try {
      const scanRef = doc(db, scanPath);
      
      await updateDoc(scanRef, {
        extractedData: editedData,
        status: 'completed',
        modifiedAt: serverTimestamp()
      });

      // Update dataset count
      const datasetRef = doc(db, 'datasets', datasetId);
      await updateDoc(datasetRef, {
        entryCount: increment(1),
        modifiedAt: serverTimestamp()
      });
      
      onNavigate('DATASET');
    } catch (error) {
      handleFirestoreError(error, OperationType.UPDATE, scanPath);
    } finally {
      setIsSaving(false);
    }
  };

  const questions = Array.from({ length: 25 }, (_, i) => `q${i + 1}`);

  return (
    <div className="pt-24 px-4 md:px-8 pb-32">
      <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold tracking-tight text-on-surface leading-none">Review Data</h2>
          <p className="mt-2 text-on-surface-variant font-medium">Scan ID: #{scan.id.slice(0, 8)} • Template: Standard 25-Q</p>
        </div>
        <div className={`flex items-center gap-2 px-4 py-2 rounded-xl border ${scan.confidence < 60 ? 'bg-error-container/20 border-error/20' : 'bg-surface-container-low border-outline-variant/15'}`}>
          <span className={`w-3 h-3 rounded-full ${scan.confidence < 60 ? 'bg-error animate-pulse' : 'bg-green-500'}`}></span>
          <span className="text-sm font-bold text-on-surface">
            {scan.confidence < 60 ? 'Review Required' : 'High Confidence'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Image Preview */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-surface-container-low rounded-3xl overflow-hidden border border-outline-variant/10 relative aspect-[1/1.414]">
            <img 
              src={scan.alignedImageUrl || scan.pages?.[0]} 
              alt="Aligned Form" 
              referrerPolicy="no-referrer" 
              className="w-full h-full object-contain" 
            />
            {/* Highlight active question region (mock) */}
            <div 
              className="absolute border-2 border-primary bg-primary/10 transition-all duration-300"
              style={{
                top: `${10 + activeQuestion * 3.5}%`,
                left: '15%',
                width: '70%',
                height: '3.5%'
              }}
            />
          </div>
        </div>

        {/* Correction UI */}
        <div className="lg:col-span-5 space-y-6">
          <div className="bg-surface-container-low rounded-3xl p-6 border border-outline-variant/10">
            <div className="flex items-center justify-between mb-6">
              <h3 className="font-black text-lg uppercase tracking-tight">Question Navigator</h3>
              <div className="flex gap-2">
                <button 
                  onClick={() => setActiveQuestion(Math.max(0, activeQuestion - 1))}
                  className="p-2 bg-surface-container-highest rounded-xl hover:bg-primary/10 transition-colors"
                >
                  <ChevronLeft size={20} />
                </button>
                <button 
                  onClick={() => setActiveQuestion(Math.min(24, activeQuestion + 1))}
                  className="p-2 bg-surface-container-highest rounded-xl hover:bg-primary/10 transition-colors"
                >
                  <ChevronRight size={20} />
                </button>
              </div>
            </div>

            <div className="space-y-6">
              <div className="p-5 bg-surface-container-lowest rounded-2xl border border-outline-variant/5">
                <div className="flex justify-between items-center mb-4">
                  <span className="text-xs font-black text-primary uppercase tracking-widest">Question {activeQuestion + 1}</span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${scan.fieldsConfidence?.[`q${activeQuestion + 1}`] < 60 ? 'bg-error text-white' : 'bg-green-100 text-green-800'}`}>
                    {Math.round(scan.fieldsConfidence?.[`q${activeQuestion + 1}`] || 0)}% Confidence
                  </span>
                </div>
                
                <div className="grid grid-cols-6 gap-2">
                  {[1, 2, 3, 4, 5, 6].map((val) => (
                    <button
                      key={val}
                      onClick={() => setEditedData({ ...editedData, [`q${activeQuestion + 1}`]: val })}
                      className={`h-12 rounded-xl font-black transition-all ${
                        editedData[`q${activeQuestion + 1}`] === val
                          ? 'bg-primary text-on-primary scale-105 shadow-md'
                          : 'bg-surface-container-highest text-on-surface-variant hover:bg-primary/10'
                      }`}
                    >
                      {val}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-5 gap-2 max-h-60 overflow-y-auto p-1">
                {questions.map((q, i) => (
                  <button
                    key={q}
                    onClick={() => setActiveQuestion(i)}
                    className={`aspect-square rounded-lg text-xs font-bold transition-all border-2 ${
                      activeQuestion === i 
                        ? 'border-primary bg-primary/10 text-primary' 
                        : scan.fieldsConfidence?.[q] < 60 
                          ? 'border-error/30 bg-error/5 text-error' 
                          : 'border-transparent bg-surface-container-highest text-on-surface-variant'
                    }`}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <button 
            onClick={handleConfirm}
            disabled={isSaving}
            className="w-full py-4 bg-primary text-on-primary rounded-2xl font-black shadow-lg hover:shadow-primary/20 transition-all flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-50"
          >
            {isSaving ? (
              <div className="w-5 h-5 border-2 border-on-primary border-t-transparent rounded-full animate-spin"></div>
            ) : (
              <>
                <CheckCircle2 size={20} />
                Confirm & Save Record
              </>
            )}
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

function DatasetView({ onNavigate, datasets, user }: { onNavigate: (s: Screen) => void, datasets: any[], user: User }) {
  const [scans, setScans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(datasets[0]?.id || '');

  useEffect(() => {
    if (!selectedDatasetId) return;
    setLoading(true);
    const scansPath = `datasets/${selectedDatasetId}/scans`;
    const scansQuery = query(collection(db, scansPath), orderBy('createdAt', 'desc'));
    const unsub = onSnapshot(scansQuery, (snapshot) => {
      setScans(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
      setLoading(false);
    }, (error) => {
      handleFirestoreError(error, OperationType.LIST, scansPath);
    });
    return () => unsub();
  }, [selectedDatasetId]);

  const handleCreateDataset = async () => {
    const name = prompt("Enter dataset name:");
    if (!name) return;
    
    const datasetsPath = 'datasets';
    try {
      await addDoc(collection(db, datasetsPath), {
        name,
        ownerId: user.uid,
        createdAt: serverTimestamp(),
        modifiedAt: serverTimestamp(),
        entryCount: 0,
        type: 'medical'
      });
    } catch (error) {
      handleFirestoreError(error, OperationType.CREATE, datasetsPath);
    }
  };

  const exportCSV = () => {
    if (scans.length === 0) return;
    
    const headers = ['FormID', ...Array.from({ length: 25 }, (_, i) => `Q${i + 1}`)];
    const rows = scans.map(scan => {
      const data = scan.extractedData || {};
      return [
        scan.id,
        ...Array.from({ length: 25 }, (_, i) => data[`q${i + 1}`] || '')
      ];
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
                Showing <span className="text-primary font-bold">{scans.length}</span> entries.
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
          </div>
        </div>
      </section>

      <div className="bg-surface-container-low rounded-3xl overflow-hidden shadow-sm border border-outline-variant/10">
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
              ) : scans.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-on-surface-variant font-medium italic">
                    No entries found in this dataset.
                  </td>
                </tr>
              ) : (
                scans.map((scan) => (
                  <tr key={scan.id} className="hover:bg-surface-container-highest/50 transition-colors">
                    <td className="px-6 py-4">
                      <span className="font-mono text-xs font-bold text-primary">#{scan.id.slice(0, 8)}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter ${
                        scan.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
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
                        <span className="text-[10px] font-bold">{Math.round(scan.confidence)}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map(i => (
                          <span key={i} className="w-6 h-6 flex items-center justify-center bg-surface-container-highest rounded text-[10px] font-bold">
                            {scan.extractedData?.[`q${i}`] || '-'}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <button 
                        onClick={() => {
                          // In AppContent, we'd need to set currentScan and currentScreen
                          // For now, this is a placeholder for the action
                        }}
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
    </div>
  );
}
