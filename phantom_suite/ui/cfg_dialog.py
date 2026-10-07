"""
PhantomSuite Interactive Control Flow Graph (CFG) Dialog
Renders an interactive node graph of basic blocks with zoom/pan,
colored edge routing (taken, fallthrough, unconditional), branch inversion, and NOP patching.
"""

from typing import Optional, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsPathItem, QMessageBox
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QPainter, QPainterPath, QFont

from phantom_suite.core.cfg_engine import CFGEngine, ControlFlowGraph, BasicBlock


class BlockNodeItem(QGraphicsRectItem):
    """Represents a basic block card on the CFG canvas."""

    def __init__(self, block: BasicBlock, on_invert_cb=None, parent=None):
        inst_count = len(block.instructions)
        h = 40 + inst_count * 18
        w = 260
        super().__init__(block.x, block.y, w, h, parent)
        self.block = block
        self.on_invert_cb = on_invert_cb

        self.setPen(QPen(QColor("#00f0ff"), 1.5))
        self.setBrush(QBrush(QColor("#0b0e14")))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        # Header: Block ID & Range
        header_text = f"Block #{block.id} [0x{block.start_addr:X} - 0x{block.end_addr:X}]"
        header_item = QGraphicsTextItem(header_text, self)
        header_item.setFont(QFont("Monospace", 9, QFont.Bold))
        header_item.setDefaultTextColor(QColor("#ffb700"))
        header_item.setPos(block.x + 8, block.y + 4)

        # Instruction lines
        y_offset = block.y + 26
        for ins in block.instructions:
            color = "#00ff9d" if ins.is_branch else ("#ff0055" if ins.is_ret else "#c5d1eb")
            line_str = f"0x{ins.address:X}:  {ins.mnemonic:<6} {ins.op_str}"
            t_item = QGraphicsTextItem(line_str, self)
            t_item.setFont(QFont("Monospace", 8))
            t_item.setDefaultTextColor(QColor(color))
            t_item.setPos(block.x + 8, y_offset)
            y_offset += 18


class CFGDialog(QDialog):
    """Interactive Control Flow Graph Viewer with Zoom & Pan."""

    def __init__(self, pid: int, entry_address: int, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.entry_address = entry_address
        self.cfg: Optional[ControlFlowGraph] = None

        self.setWindowTitle(f"Control Flow Graph // Function: 0x{entry_address:X}")
        self.resize(960, 680)
        self._init_ui()
        self._load_cfg()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Toolbar
        bar = QHBoxLayout()
        info_lbl = QLabel(f"Function CFG Target: <b>0x{self.entry_address:X}</b>")
        info_lbl.setStyleSheet("color: #00f0ff; font-size: 13px;")
        bar.addWidget(info_lbl)

        bar.addStretch()

        self.stats_lbl = QLabel("0 blocks | 0 edges")
        self.stats_lbl.setStyleSheet("color: #7d90b3; font-size: 11px;")
        bar.addWidget(self.stats_lbl)

        invert_btn = QPushButton("🔄 Invert Last Branch")
        invert_btn.setObjectName("accent_btn")
        invert_btn.clicked.connect(self._invert_entry_branch)
        bar.addWidget(invert_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bar.addWidget(close_btn)

        layout.addLayout(bar)

        # Graphics Scene & View
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor("#080a0f")))

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setStyleSheet("border: 1px solid #1c2333; background-color: #080a0f;")
        layout.addWidget(self.view, 1)

    def _load_cfg(self):
        self.cfg = CFGEngine.build_cfg(self.pid, self.entry_address, max_bytes=1024)
        if not self.cfg or not self.cfg.blocks:
            QMessageBox.warning(self, "CFG Error", f"Failed to disassemble function at 0x{self.entry_address:X}")
            return

        self.scene.clear()
        total_edges = 0

        # Draw Nodes
        node_items: Dict[int, BlockNodeItem] = {}
        for bb in self.cfg.blocks.values():
            node = BlockNodeItem(bb)
            self.scene.addItem(node)
            node_items[bb.id] = node
            total_edges += len(bb.successors)

        # Draw Edges (Bezier curves)
        for bb in self.cfg.blocks.values():
            src_node = node_items[bb.id]
            src_rect = src_node.rect()
            src_bottom = QPointF(src_rect.x() + src_rect.width() / 2, src_rect.y() + src_rect.height())

            for succ_id in bb.successors:
                if succ_id not in node_items:
                    continue
                dst_node = node_items[succ_id]
                dst_rect = dst_node.rect()
                dst_top = QPointF(dst_rect.x() + dst_rect.width() / 2, dst_rect.y())

                edge_type = bb.edge_types.get(succ_id, "unconditional")
                if edge_type == "taken":
                    edge_color = QColor("#00ff9d") # Green
                elif edge_type == "fallthrough":
                    edge_color = QColor("#ff0055") # Red
                else:
                    edge_color = QColor("#00f0ff") # Blue / Cyan

                path = QPainterPath(src_bottom)
                c1 = QPointF(src_bottom.x(), (src_bottom.y() + dst_top.y()) / 2)
                c2 = QPointF(dst_top.x(), (src_bottom.y() + dst_top.y()) / 2)
                path.cubicTo(c1, c2, dst_top)

                edge_item = QGraphicsPathItem(path)
                edge_item.setPen(QPen(edge_color, 2.0))
                self.scene.addItem(edge_item)

        self.stats_lbl.setText(f"{len(self.cfg.blocks)} blocks | {total_edges} edges")

    def _invert_entry_branch(self):
        if not self.cfg:
            return
        entry = self.cfg.get_entry_block()
        if not entry or not entry.instructions:
            return
        last_ins = entry.instructions[-1]
        if not last_ins.is_conditional:
            QMessageBox.information(self, "No Branch", "Entry block does not end with a conditional jump.")
            return

        if CFGEngine.invert_branch(self.pid, last_ins.address):
            QMessageBox.information(self, "Branch Inverted", f"Inverted branch at 0x{last_ins.address:X} successfully!")
            self._load_cfg()
        else:
            QMessageBox.critical(self, "Error", "Failed to invert branch instruction.")
