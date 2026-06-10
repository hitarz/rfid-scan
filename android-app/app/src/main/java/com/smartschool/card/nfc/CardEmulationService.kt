package com.smartschool.card.nfc

import android.nfc.cardemulation.HostApduService
import android.os.Bundle
import com.smartschool.card.SmartSchoolApp

/**
 * HCE: передає постійний card_uid на ESP32 без інтернету на телефоні.
 * ID зберігається локально після входу / створення картки.
 */
class CardEmulationService : HostApduService() {

    override fun processCommandApdu(commandApdu: ByteArray, extras: Bundle?): ByteArray {
        val cardUid = (application as SmartSchoolApp).sessionManager.cardUid
            ?.uppercase()
            ?.filter { it in '0'..'9' || it in 'A'..'F' }
            ?: return STATUS_FAILED

        if (cardUid.length != 8) return STATUS_FAILED

        if (isSelectAid(commandApdu, SMART_SCHOOL_AID) || isSelectAid(commandApdu, NDEF_AID)) {
            return STATUS_OK
        }

        // GET CARD UID: 80 CB 00 00 08
        if (commandApdu.size >= 5 &&
            commandApdu[0] == 0x80.toByte() &&
            commandApdu[1] == 0xCB.toByte()
        ) {
            return cardUid.toByteArray(Charsets.US_ASCII) + STATUS_OK
        }

        // READ BINARY (NDEF): 00 B0 ...
        if (commandApdu.size >= 2 && commandApdu[1] == 0xB0.toByte()) {
            return buildNdefPayload(cardUid) + STATUS_OK
        }

        return STATUS_OK
    }

    override fun onDeactivated(reason: Int) = Unit

    private fun buildNdefPayload(cardUid: String): ByteArray {
        val text = "SSCARD:$cardUid"
        val lang = "en".toByteArray(Charsets.US_ASCII)
        val textBytes = text.toByteArray(Charsets.US_ASCII)
        val payload = ByteArray(1 + lang.size + textBytes.size)
        payload[0] = lang.size.toByte()
        lang.copyInto(payload, 1)
        textBytes.copyInto(payload, 1 + lang.size)
        val record = ByteArray(3 + payload.size)
        record[0] = 0xD1.toByte()
        record[1] = 0x01
        record[2] = payload.size.toByte()
        payload.copyInto(record, 3)
        val ndef = ByteArray(2 + record.size)
        ndef[0] = 0x00
        ndef[1] = record.size.toByte()
        record.copyInto(ndef, 2)
        return ndef
    }

    private fun isSelectAid(apdu: ByteArray, aid: ByteArray): Boolean {
        if (apdu.size < 5 || apdu[0] != 0x00.toByte() || apdu[1] != 0xA4.toByte()) {
            return false
        }
        val lc = apdu[4].toInt() and 0xFF
        if (apdu.size < 5 + lc || lc != aid.size) return false
        for (i in aid.indices) {
            if (apdu[5 + i] != aid[i]) return false
        }
        return true
    }

    companion object {
        private val SMART_SCHOOL_AID = byteArrayOf(
            0xF0.toByte(), 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
        )
        private val NDEF_AID = byteArrayOf(
            0xD2.toByte(), 0x76, 0x00, 0x00, 0x85.toByte(), 0x01, 0x01,
        )
        private val STATUS_OK = byteArrayOf(0x90.toByte(), 0x00)
        private val STATUS_FAILED = byteArrayOf(0x6F.toByte(), 0x00)
    }
}
