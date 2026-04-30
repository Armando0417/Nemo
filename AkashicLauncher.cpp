#include <iostream>
#include <string>
#include <filesystem>
#include <winsock2.h>
#include <windows.h>
#include <shellapi.h>
#include <ws2tcpip.h>

#pragma comment(lib, "ws2_32.lib")

// -- Config -------------------------------------------------------
constexpr const char *JF_EXE = R"(D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\engine\jellyfin.exe)";
constexpr const char *JF_DATA = R"(D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\configurations\data)";
constexpr const char *JF_CACHE = R"(D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\configurations\cache)";
constexpr const char *JF_LOGS = R"(D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\configurations\logs)";
constexpr const char *SERVE_DIR = R"(D:\Wandering_Sea)";
constexpr int JF_PORT = 4004;
constexpr int HTTP_PORT = 12500;

// gate_loader.html URL with params pre-filled for this gate
constexpr const char *GATE_URL =
    "http://localhost:12500/gate_loader.html"
    "?name=AKASHIC+RECORDS"
    "&port=4004"
    "&subtitle=The+Eternal+Media+Archive"
    "&class=RESTRICTED+ACCESS"
    "&loader_rev=20260329a";

// -- Types --------------------------------------------------------
enum class ServerStatus
{
    NOT_RUNNING,
    STARTING_UP,
    READY,
    ERR
};

// -- Helpers ------------------------------------------------------
void printTitle()
{
    std::cout << "\n";
    std::cout << "  ===================================================\n";
    std::cout << "\n";
    std::cout << "          A K A S H I C   R E C O R D S\n";
    std::cout << "          -------------------------------\n";
    std::cout << "            The Eternal Media Archive\n";
    std::cout << "\n";
    std::cout << "  ===================================================\n";
    std::cout << "\n";
}

ServerStatus checkHealth(int port)
{
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0)
        return ServerStatus::ERR;

    SOCKET sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock == INVALID_SOCKET)
    {
        WSACleanup();
        return ServerStatus::ERR;
    }

    DWORD timeout = 3000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof(timeout));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char *)&timeout, sizeof(timeout));

    sockaddr_in hint{};
    hint.sin_family = AF_INET;
    hint.sin_port = htons(static_cast<u_short>(port));
    hint.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (connect(sock, (sockaddr *)&hint, sizeof(hint)) == SOCKET_ERROR)
    {
        closesocket(sock);
        WSACleanup();
        return ServerStatus::NOT_RUNNING;
    }

    const char *request = "GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n";
    if (send(sock, request, (int)strlen(request), 0) == SOCKET_ERROR)
    {
        closesocket(sock);
        WSACleanup();
        return ServerStatus::ERR;
    }

    char buffer[4096]{};
    std::string response;
    int bytes;
    while ((bytes = recv(sock, buffer, 4095, 0)) > 0)
    {
        response.append(buffer, bytes);
        ZeroMemory(buffer, sizeof(buffer));
    }

    closesocket(sock);
    WSACleanup();

    if (response.find("Healthy") != std::string::npos)
        return ServerStatus::READY;
    if (response.find("Degraded") != std::string::npos)
        return ServerStatus::STARTING_UP;
    return ServerStatus::ERR;
}

// Launch a process silently (no window). Returns true on success.
bool launchSilent(const std::string &cmd, const char *workingDir = nullptr)
{
    STARTUPINFOA si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION pi{};

    std::string mutableCmd = cmd; // CreateProcessA needs writable buffer
    return CreateProcessA(
        NULL,
        mutableCmd.data(),
        NULL, NULL,
        FALSE,
        CREATE_NO_WINDOW,
        NULL,
        workingDir,
        &si, &pi);
}

// Launch Jellyfin minimized (it has its own window we want visible-ish)
bool launchJellyfin()
{
    std::string cmd = std::string("\"") + JF_EXE + "\"" + " --datadir \"" + JF_DATA + "\"" + " --cachedir \"" + JF_CACHE + "\"" + " --logdir \"" + JF_LOGS + "\"";

    STARTUPINFOA si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_MINIMIZE;

    PROCESS_INFORMATION pi{};
    std::string mutableCmd = cmd;

    return CreateProcessA(NULL, mutableCmd.data(), NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi);
}

void openBrowser(const char *url)
{
    ShellExecuteA(NULL, "open", url, NULL, NULL, SW_SHOWNORMAL);
}

// -- Main ---------------------------------------------------------
int main()
{
    printTitle();

    // Pre-flight: check exe exists
    if (!std::filesystem::exists(JF_EXE))
    {
        std::cout << "  [!] FATAL: jellyfin.exe not found\n";
        std::cout << "      " << JF_EXE << "\n\n";
        std::cout << "  Press any key to exit...\n";
        std::cin.get();
        return 1;
    }

    // Check if Jellyfin is already up
    ServerStatus status = checkHealth(JF_PORT);
    bool jellyfinWasRunning = (status == ServerStatus::READY || status == ServerStatus::STARTING_UP);

    if (jellyfinWasRunning)
    {
        std::cout << "  [=] Gate already active on port " << JF_PORT << "\n";
    }
    else
    {
        // Create dirs if needed
        std::filesystem::create_directories(JF_DATA);
        std::filesystem::create_directories(JF_CACHE);
        std::filesystem::create_directories(JF_LOGS);

        std::cout << "  [+] Opening Gate...\n\n";
        std::cout << "      Data:  " << JF_DATA << "\n";
        std::cout << "      Cache: " << JF_CACHE << "\n";
        std::cout << "      Logs:  " << JF_LOGS << "\n";
        std::cout << "      Port:  " << JF_PORT << "\n\n";

        if (!launchJellyfin())
        {
            std::cout << "  [!] Failed to launch jellyfin.exe (error #" << GetLastError() << ")\n\n";
            std::cout << "  Press any key to exit...\n";
            std::cin.get();
            return 1;
        }
    }

    // Start the local HTTP server to serve gate_loader.html
    // (python -m http.server 12500 from D:\Wandering_Sea)
    std::string serveCmd = "python -m http.server " + std::to_string(HTTP_PORT);
    launchSilent(serveCmd, SERVE_DIR);
    // Give it a moment to bind
    Sleep(800);

    // Open gate loader in browser — it polls Jellyfin and redirects when ready
    std::cout << "  [~] Opening gate loader at http://localhost:" << HTTP_PORT << "\n\n";
    openBrowser(GATE_URL);

    std::cout << "  Gate is opening. Browser will redirect when Jellyfin is ready.\n";
    std::cout << "  (This window can be closed — Jellyfin keeps running)\n\n";
    std::cout << "  Press any key to exit...\n";
    std::cin.get();

    return 0;
}
