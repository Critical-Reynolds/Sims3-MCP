using System;
using System.Collections.Generic;
using Sims3.SimIFace;
using Sims3.UI;

namespace Sims3Mcp
{
    // Standard Sims 3 script-mod entry point: the game parses the _XML tuning
    // resource whose instance id is FNV64("Sims3Mcp.Instantiator"), which
    // touches this [Tunable] field and runs the static constructor.
    public class Instantiator
    {
        [Tunable] protected static bool kInstantiator = false;

        public const string ModVersion = "0.1.0";

        static Instantiator()
        {
            World.OnWorldLoadFinishedEventHandler += OnWorldLoadFinished;
            World.OnWorldQuitEventHandler += OnWorldQuit;
            Handlers.RegisterAll();
            // Open right away so the server can see the mod is loaded even
            // before a world is (state stays 0 until a world finishes loading).
            Mailbox.Open();
        }

        static void OnWorldLoadFinished(object sender, EventArgs e)
        {
            Mailbox.Close();
            Mailbox.Open();
            Mailbox.SetWorldLoaded(true);
            PollTask.Start();
        }

        static void OnWorldQuit(object sender, EventArgs e)
        {
            PollTask.Halt();
            Mailbox.Close();
        }
    }

    // Simulator task that services the mailbox every tick on the game thread.
    public class PollTask : Task
    {
        static PollTask sInstance;
        bool mRunning = true;

        public static void Start()
        {
            Halt();
            sInstance = new PollTask();
            Simulator.AddObject(sInstance);
        }

        public static void Halt()
        {
            if (sInstance != null)
            {
                sInstance.mRunning = false;
                sInstance = null;
            }
        }

        public override void Simulate()
        {
            bool announced = false;
            int ticks = 0;
            while (mRunning)
            {
                try { Mailbox.Poll(); }
                catch (Exception) { }
                if (!announced && ++ticks > 300)  // let the HUD finish loading first
                {
                    announced = true;
                    try
                    {
                        StyledNotification.Show(new StyledNotification.Format(
                            "Sims3MCP " + Instantiator.ModVersion + " connected", StyledNotification.NotificationStyle.kSystemMessage));
                    }
                    catch (Exception) { }
                }
                Simulator.Sleep(0);
            }
            Simulator.DestroyObject(ObjectId);
        }
    }
}
