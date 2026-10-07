// Dumps every type and member signature from the game assemblies to a text
// file, one member per line ("Namespace.Type :: member"), for grepping.
// Build: csc /out:build\apidump.exe tools\apidump.cs
// Run:   build\apidump.exe build\refs build\api.txt
using System;
using System.IO;
using System.Reflection;
using System.Text;

static class ApiDump
{
    static string sRefDir;

    static int Main(string[] args)
    {
        sRefDir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.ReflectionOnlyAssemblyResolve += delegate(object s, ResolveEventArgs e)
        {
            string name = new AssemblyName(e.Name).Name;
            string path = Path.Combine(sRefDir, name + ".dll");
            if (name != "mscorlib" && File.Exists(path)) return Assembly.ReflectionOnlyLoadFrom(path);
            return Assembly.ReflectionOnlyLoad(e.Name);
        };
        BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance
                           | BindingFlags.Static | BindingFlags.DeclaredOnly;
        using (StreamWriter w = new StreamWriter(args[1], false, new UTF8Encoding(false)))
        {
            foreach (string file in Directory.GetFiles(sRefDir, "*.dll"))
            {
                string asmName = Path.GetFileNameWithoutExtension(file);
                if (asmName == "mscorlib" || asmName == "System" || asmName == "System.Xml") continue;
                Assembly asm = Assembly.ReflectionOnlyLoadFrom(file);
                Type[] types;
                try { types = asm.GetTypes(); }
                catch (ReflectionTypeLoadException ex) { types = ex.Types; }
                foreach (Type t in types)
                {
                    if (t == null) continue;
                    string tn = t.FullName;
                    string kind = t.IsEnum ? "enum" : t.IsInterface ? "interface" : t.IsValueType ? "struct" : "class";
                    string bt = "";
                    try { if (t.BaseType != null) bt = " : " + t.BaseType.FullName; } catch { }
                    w.WriteLine("{0} [{1}] {2}{3}", tn, asmName, kind, bt);
                    try
                    {
                        foreach (MemberInfo m in t.GetMembers(all))
                        {
                            string line;
                            try { line = Describe(m); } catch (Exception ex) { line = m.Name + " <" + ex.GetType().Name + ">"; }
                            if (line != null) w.WriteLine("{0} :: {1}", tn, line);
                        }
                    }
                    catch (Exception ex) { w.WriteLine("{0} :: <members failed: {1}>", tn, ex.Message); }
                }
            }
        }
        return 0;
    }

    static string Vis(MethodBase m)
    {
        if (m == null) return "";
        return (m.IsPublic ? "public " : m.IsFamily ? "protected " : m.IsAssembly ? "internal " : "private ")
               + (m.IsStatic ? "static " : "") + (m.IsVirtual ? "virtual " : "");
    }

    static string TN(Type t)
    {
        if (t == null) return "?";
        if (t.IsGenericParameter) return t.Name;
        if (t.IsGenericType)
        {
            StringBuilder sb = new StringBuilder(t.Name.Split('`')[0]).Append('<');
            Type[] a = t.GetGenericArguments();
            for (int i = 0; i < a.Length; i++) { if (i > 0) sb.Append(','); sb.Append(TN(a[i])); }
            return sb.Append('>').ToString();
        }
        return t.IsNested ? TN(t.DeclaringType) + "+" + t.Name : t.Name;
    }

    static string Params(ParameterInfo[] ps)
    {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < ps.Length; i++)
        {
            if (i > 0) sb.Append(", ");
            sb.Append(TN(ps[i].ParameterType)).Append(' ').Append(ps[i].Name);
        }
        return sb.ToString();
    }

    static string Describe(MemberInfo m)
    {
        switch (m.MemberType)
        {
            case MemberTypes.Field:
                FieldInfo f = (FieldInfo)m;
                if (f.Name.Contains("<")) return null;
                return "field " + (f.IsPublic ? "public " : f.IsFamily ? "protected " : f.IsAssembly ? "internal " : "private ")
                       + (f.IsStatic ? "static " : "") + TN(f.FieldType) + " " + f.Name;
            case MemberTypes.Property:
                PropertyInfo p = (PropertyInfo)m;
                MethodInfo g = p.GetGetMethod(true), s = p.GetSetMethod(true);
                return "prop " + Vis(g ?? s) + TN(p.PropertyType) + " " + p.Name
                       + " {" + (g != null ? " get;" : "") + (s != null ? " set;" : "") + " }";
            case MemberTypes.Method:
                MethodInfo mi = (MethodInfo)m;
                if (mi.IsSpecialName) return null;
                return "method " + Vis(mi) + TN(mi.ReturnType) + " " + mi.Name + "(" + Params(mi.GetParameters()) + ")";
            case MemberTypes.Constructor:
                ConstructorInfo c = (ConstructorInfo)m;
                return "ctor " + Vis(c) + "(" + Params(c.GetParameters()) + ")";
            case MemberTypes.Event:
                return "event " + TN(((EventInfo)m).EventHandlerType) + " " + m.Name;
            case MemberTypes.NestedType:
                return null;
        }
        return null;
    }
}
