# Bambu Plug-in Lifecycle Contract

## Failure addressed

TinManX1 could crash during normal application shutdown after the Bambu LAN
plug-in had been used. `GUI_App::shutdown()` deleted the network singleton,
then a later `GUI_App` destructor called the BambuSource release path. That
path reacquired the deleted singleton through a `std::once_flag` factory and
dereferenced a permanent null pointer.

The old source wrapper also had two incompatible `StaticBambuLib` class
definitions in separate translation units, kept unregistered raw copies of a
mutable function table, and allowed a module reload to invalidate functions
still owned by a live tunnel.

## Ownership rules

1. `BBLNetworkPlugin` is a process-lifetime manager. Its agent and callable
   function table are explicitly stopped, but the manager object is never
   deleted during wxWidgets teardown.
2. `unload()` destroys the proprietary agent before clearing the entry points
   that created it. Calling `shutdown()` or `unload()` repeatedly is valid.
3. Proprietary networking and source images stay mapped until process exit.
   Their private workers are not covered by a documented global join barrier,
   so in-process unmapping is unsafe.
4. Every `PrinterFileSystem` session owns an immutable snapshot of the complete
   BambuSource ABI. A tunnel is created, read, closed, and destroyed through
   the same snapshot.
5. Active file-system owners are registered as weak pointers. Shutdown first
   promotes them under the registry lock, then releases that lock before
   signaling each worker. This prevents both use-after-free and lock inversion.
6. BambuSource's shared function table remains process-lifetime because the
   GStreamer and platform media backends do not expose a complete global
   callback/thread barrier. It is never cleared beneath a late media finalizer.
7. On macOS both proprietary images are opened with `RTLD_NODELETE`. Exit
   guards are registered after module initialization and agent construction so
   they run before finalizers registered by the closed-source library.

## Shutdown order

1. Mark application shutdown once; later calls are no-ops.
2. Stop file-system sessions and prevent new network callbacks.
3. Cancel and join TaskManager's scheduler and per-print workers.
4. Disconnect and delete the public `NetworkAgent` wrapper.
5. Destroy the proprietary agent while its entry point is valid.
6. During `GUI_App` destruction, wait for registered file-system workers.
7. Disable the networking API but leave proprietary images mapped.
8. Arm the macOS process-finalizer guard after ordinary cleanup finishes. A
   later-registered fallback also covers quit requests received during startup.
9. Let the operating system reclaim process-lifetime module mappings.

## Reload rule

Networking plug-ins use versioned paths. A hot reload destroys the old agent,
clears its callable table, and maps the replacement beside the resident old
image. Existing BambuSource tunnels keep their stable source table; source
updates take effect after application restart.

## Regression coverage

The utility test suite verifies that repeated shutdown and direct unload keep
the same manager address, leave no agent, and leave no callable networking
module. Release validation also includes repeated launch/quit cycles with the
installed Bambu plug-in present and a crash-report scan after each cycle.
