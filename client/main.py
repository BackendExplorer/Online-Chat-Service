import streamlit as st
from gui import AppController, GUIManager


if __name__ == "__main__":
    # アプリケーション制御クラスを初期化
    controller = AppController()

    # GUIマネージャを作成し、UIのセットアップとレンダリングを実行
    gui  = GUIManager(controller)
    gui.setup()
    gui.render()
