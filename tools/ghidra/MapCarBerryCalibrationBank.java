// Map CarBerry packed calibration bank from imported original_carberry.bin.
// @category DKmode.CarBerry
// @author DKmode research

import java.util.List;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.FileBytes;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.address.Address;

public class MapCarBerryCalibrationBank extends GhidraScript {

    private static final long FILE_OFFSET = 0x20000L;
    private static final long BANK_SIZE   = 0x8000L;
    private static final long ADDRESS     = 0x28000L;
    private static final long REQUIRED_FILE_SIZE = FILE_OFFSET + BANK_SIZE;

    @Override
    protected void run() throws Exception {
        if (currentProgram == null) {
            printerr("Open the imported original_carberry.bin program first.");
            return;
        }
        Memory memory = currentProgram.getMemory();
        Address start = toAddr(ADDRESS);
        MemoryBlock existing = memory.getBlock(start);
        if (existing != null) {
            println("Address 0x028000 is already mapped in block: " + existing.getName());
            println("No changes made. Checking calibration bytes below.");
            verify(memory);
            return;
        }

        List<FileBytes> sources = memory.getAllFileBytes();
        FileBytes input = null;
        for (FileBytes fb : sources) {
            if (fb.getSize() >= REQUIRED_FILE_SIZE) {
                input = fb;
                break;
            }
        }
        if (input == null) {
            printerr("Could not find source FileBytes with at least 0x28000 bytes.");
            printerr("Re-import the 160-KiB original_carberry.bin as Binary, then rerun.");
            return;
        }

        // This changes ONLY the Ghidra program database, not the .bin on disk.
        MemoryBlock bank = memory.createInitializedBlock(
            "CARBERRY_CAL", start, input, FILE_OFFSET, BANK_SIZE, false);
        bank.setRead(true);
        bank.setWrite(false);
        bank.setExecute(false);
        bank.setComment("CarBerry HC16 suspected ROM calibration bank: " +
            "runtime 0x28000..0x2FFFF from original BIN 0x20000..0x27FFF. " +
            "Independent MCU memory decode confirmation pending.");

        println("Mapped " + bank.getName() + " " + bank.getStart() +
            ".." + bank.getEnd() + " using original BIN FileBytes @ 0x20000.");
        verify(memory);
    }

    private void verify(Memory memory) throws Exception {
        // Markers independently observed in original 160-KiB BIN.
        check(memory, 0x2865cL, new int[]{0x80, 0x00, 0x7a, 0x1c, 0x1e, 0x00, 0x00});
        check(memory, 0x28667L, new int[]{0x00, 0x40, 0x00, 0x40, 0x00, 0x40, 0x3f, 0x7d});
        check(memory, 0x293f8L, new int[]{0x82, 0x04, 0x00, 0x60, 0x00, 0x24});
    }

    private void check(Memory memory, long addr, int[] expected) throws Exception {
        StringBuilder actualHex = new StringBuilder();
        boolean ok = true;
        for (int i = 0; i < expected.length; i++) {
            int value = memory.getByte(toAddr(addr + i)) & 0xff;
            actualHex.append(String.format("%02X ", value));
            if (value != expected[i]) ok = false;
        }
        println(String.format("0x%05X  %s  %s", addr,
            actualHex.toString().trim(), ok ? "MATCH" : "MISMATCH - check imported BIN/mapping"));
    }
}
