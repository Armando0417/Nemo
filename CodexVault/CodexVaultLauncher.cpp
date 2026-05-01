#include <filesystem>
#include <iostream>
#include <string>
#include <windows.h>
#include <shellapi.h>

namespace fs = std::filesystem;

constexpr const wchar_t *VAULT_ROOT = L"E:\\Wandering_Sea\\Gates\\Codex-Vault";
constexpr const wchar_t *SERVE_DIR = L"D:\\Wandering_Sea";
constexpr int FRONTEND_PORT = 6221;
constexpr int HTTP_PORT = 12502;
constexpr const wchar_t *GATE_URL =
    L"http://localhost:12502/gate_loader.html"
    L"?name=CODEX+VAULT"
    L"&port=6221"
    L"&subtitle=The+Indexed+Archive"
    L"&class=RESTRICTED+ACCESS"
    L"&loader_rev=20260329a";

std::string widenToAnsi(const std::wstring &value)
{
    if (value.empty())
    {
        return {};
    }

    int size = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (size <= 0)
    {
        return {};
    }

    std::string result(size - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, result.data(), size, nullptr, nullptr);
    return result;
}

void printTitle()
{
    std::cout << "\n";
    std::cout << "  ===================================================\n";
    std::cout << "\n";
    std::cout << "                C O D E X   V A U L T\n";
    std::cout << "                ---------------------\n";
    std::cout << "          Frontend + Indexer Launcher\n";
    std::cout << "\n";
    std::cout << "  ===================================================\n";
    std::cout << "\n";
}

std::wstring findPowerShell()
{
    const wchar_t *candidates[] = {L"pwsh.exe", L"powershell.exe"};
    wchar_t resolved[MAX_PATH];

    for (const auto *candidate : candidates)
    {
        DWORD length = SearchPathW(nullptr, candidate, nullptr, MAX_PATH, resolved, nullptr);
        if (length > 0 && length < MAX_PATH)
        {
            return resolved;
        }
    }

    return {};
}

std::wstring findPython()
{
    const wchar_t *candidates[] = {L"python.exe", L"py.exe"};
    wchar_t resolved[MAX_PATH];

    for (const auto *candidate : candidates)
    {
        DWORD length = SearchPathW(nullptr, candidate, nullptr, MAX_PATH, resolved, nullptr);
        if (length > 0 && length < MAX_PATH)
        {
            return resolved;
        }
    }

    return {};
}

HANDLE createKillOnCloseJob()
{
    HANDLE job = CreateJobObjectW(nullptr, nullptr);
    if (job == nullptr)
    {
        return nullptr;
    }

    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

    if (!SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info,
            sizeof(info)))
    {
        CloseHandle(job);
        return nullptr;
    }

    return job;
}

bool startManagedProcess(
    const std::wstring &commandLine,
    const std::wstring &workingDirectory,
    HANDLE job,
    DWORD creationFlags,
    const char *label,
    PROCESS_INFORMATION &pi)
{
    STARTUPINFOW si{};
    si.cb = sizeof(si);

    std::wstring mutableCommandLine = commandLine;
    if (!CreateProcessW(
            nullptr,
            mutableCommandLine.data(),
            nullptr,
            nullptr,
            FALSE,
            creationFlags | CREATE_SUSPENDED,
            nullptr,
            workingDirectory.c_str(),
            &si,
            &pi))
    {
        std::cout << "  [!] Failed to start " << label << " (error #" << GetLastError() << ")\n";
        return false;
    }

    if (job != nullptr && !AssignProcessToJobObject(job, pi.hProcess))
    {
        std::cout << "  [!] Failed to attach " << label << " to cleanup job (error #" << GetLastError() << ")\n";
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        ZeroMemory(&pi, sizeof(pi));
        return false;
    }

    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);
    pi.hThread = nullptr;
    return true;
}

void openBrowser(const wchar_t *url)
{
    ShellExecuteW(nullptr, L"open", url, nullptr, nullptr, SW_SHOWNORMAL);
}

int main()
{
    printTitle();

    const fs::path vaultRoot = VAULT_ROOT;
    const fs::path scriptPath = vaultRoot / "start_codex_vault.ps1";
    if (!fs::exists(scriptPath))
    {
        std::cout << "  [!] FATAL: launcher script not found\n";
        std::cout << "      " << widenToAnsi(scriptPath.wstring()) << "\n";
        return 1;
    }

    const std::wstring powerShellPath = findPowerShell();
    if (powerShellPath.empty())
    {
        std::cout << "  [!] FATAL: neither pwsh.exe nor powershell.exe was found on PATH.\n";
        return 1;
    }

    const std::wstring pythonPath = findPython();
    if (pythonPath.empty())
    {
        std::cout << "  [!] FATAL: python.exe was not found on PATH.\n";
        return 1;
    }

    std::wstring commandLine = L"\"" + powerShellPath + L"\" -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"" + scriptPath.wstring() + L"\"";
    std::wstring loaderCommandLine = L"\"" + pythonPath + L"\" -m http.server " + std::to_wstring(HTTP_PORT);

    std::cout << "  [+] Launching Codex Vault services...\n";
    std::cout << "      Script: " << widenToAnsi(scriptPath.wstring()) << "\n\n";

    HANDLE job = createKillOnCloseJob();
    if (job == nullptr)
    {
        std::cout << "  [!] Warning: failed to create cleanup job (error #" << GetLastError() << ")\n";
    }

    PROCESS_INFORMATION loaderPi{};
    if (!startManagedProcess(loaderCommandLine, SERVE_DIR, job, CREATE_NO_WINDOW, "gate loader server", loaderPi))
    {
        if (job != nullptr)
        {
            CloseHandle(job);
        }
        return 1;
    }

    Sleep(800);

    PROCESS_INFORMATION pi{};
    if (!startManagedProcess(commandLine, vaultRoot.wstring(), job, 0, "PowerShell", pi))
    {
        CloseHandle(loaderPi.hProcess);
        if (job != nullptr)
        {
            CloseHandle(job);
        }
        return 1;
    }

    std::cout << "  [~] Opening gate loader at http://localhost:" << HTTP_PORT << "\n";
    std::cout << "      Target frontend port: " << FRONTEND_PORT << "\n\n";
    openBrowser(GATE_URL);

    WaitForSingleObject(pi.hProcess, INFINITE);

    DWORD exitCode = 1;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hProcess);
    CloseHandle(loaderPi.hProcess);

    if (job != nullptr)
    {
        CloseHandle(job);
    }

    if (exitCode != 0)
    {
        std::cout << "\n  [!] Codex Vault launcher exited with code " << exitCode << ".\n";
    }

    return static_cast<int>(exitCode);
}
